"""Builds Modula.ipynb from the project's source, so the notebook can't drift from the code.
Usage: python build_notebook.py <output.ipynb> [--test]
--test adds a throwaway cell that exercises the widgets and a missing font, and keeps nothing.
"""
import json
import pprint
import re
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

ROOT = Path(__file__).resolve().parent.parent


def source(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    text = re.sub(r'\A""".*?"""\n', "", text, flags=re.S)
    text = re.sub(r"^from \.\w+ import (\([^)]*\)|[^\n]*)\n", "", text, flags=re.M)
    return text.strip() + "\n"


def between(text, start, end=None):
    i = text.index(start)
    return (text[i:text.index(end)] if end else text[i:]).strip() + "\n"


personas = json.loads((ROOT / "eval/personas.json").read_text(encoding="utf-8"))
replies = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "eval/replies").glob("*.json"))}
assert len(replies) == 72

DATA_CELL = f"""#@title Personas and recorded Claude replies (double-click to view)
PERSONAS = {pprint.pformat(personas, width=110, sort_dicts=False)}

REPLIES = {pprint.pformat(replies, width=110, sort_dicts=False)}


def load_personas():
    return PERSONAS


def load_reply(split, version, persona_id):
    return REPLIES.get(f"{{split}}_{{version}}_{{persona_id}}")
"""

SETUP = """import json
import logging
import math
import shutil
import subprocess
import sys
import unittest
from base64 import b64encode
from dataclasses import dataclass, field
from functools import lru_cache
from html import escape
from io import BytesIO
from itertools import product
from statistics import mean

import numpy as np
import pandas as pd
import ipywidgets as widgets
from IPython.display import HTML, display
from matplotlib.figure import Figure
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

# Colab doesn't have the Windows fonts named below, so matplotlib falls back to DejaVu Sans.
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
"""

EVAL = """summary, methods = evaluate("test")


def percent(value):
    return f"{math.floor(value * 100 + 0.5)}%"  # rounds 12.5% up to 13%, as on the slide


table = []
for key, label in (("fixed", "One fixed phone"), ("keyword", "Keyword rules, no AI"),
                   ("v1", "Prompt v1"), ("v2", "Prompt v2"), ("v3", "Prompt v3")):
    s = summary[key]
    table.append({
        "Method": label,
        "Clean JSON": percent(s["strict_json"]) if key.startswith("v") else "n/a",
        "Modules caught": "n/a" if key == "fixed" else percent(s["must_recall"]),
        "Modules correct": "n/a" if key == "fixed" else percent(s["must_precision"]),
        "Budget read": "n/a" if key == "fixed" else percent(s["budget_accuracy"]),
        "Fit": f"{s['fit']:.2f}",
        "Failed builds": s["failed_builds"],
    })
display(pd.DataFrame(table).set_index("Method"))

fixed_fit = {row["id"]: row["grade"]["fit"] for row in methods["fixed"]}
v3_fit = {row["id"]: row["grade"]["fit"] for row in methods["v3"]}
print(f"v3 fit is {summary['v3']['fit'] / summary['fixed']['fit']:.1f} times the fixed phone's, "
      f"and higher for {sum(v3_fit[i] > fixed_fit[i] for i in v3_fit)} of {len(v3_fit)} personas.")
"""

RUN_TESTS = """suite = unittest.TestSuite()
for case in (EngineTests, ParsingTests, ReportedResultsTests):
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
unittest.TextTestRunner(stream=sys.stdout, verbosity=1).run(suite)
"""

SHOW = """PRESET_IDS = ("d1", "d4", "t15", "d5", "d7", "d2")
SOURCE_TEXT = {
    "live": "Read by Claude.",
    "saved": "Using a saved Claude reply. Claude isn't connected on this computer.",
    "keyword": "Read by keyword matching, no AI. Claude isn't connected on this computer.",
}


def presets():
    data = load_personas()
    people = {p["id"]: {**p, "split": split} for split in ("dev", "test") for p in data[split]}
    return {people[i]["name"]: people[i] for i in PRESET_IDS}


def saved_reply(person):
    record = load_reply(person["split"], "v3", person["id"]) if person else None
    return record["reply"] if record else None


def read_request(text, person=None):
    \"\"\"Claude first. Without it, a saved reply for an example, or keyword matching.\"\"\"
    notice = None
    if is_available():
        try:
            raw = complete(PROMPTS["v3"](text))
            parsed = parse_model_reply(raw)
            if parsed.ok:
                return parsed, raw, "live", None
            notice = "Claude replied, but not in the expected format. Keyword matching ran instead."
        except LLMError as error:
            notice = f"Claude could not answer: {error} Keyword matching ran instead."

    raw = saved_reply(person)
    if raw:
        return parse_model_reply(raw), raw, "saved", None
    parsed = keyword_parse(text)
    if not notice and found_nothing(parsed):
        notice = ("Keyword matching found no words it knows in this request, so this build uses equal priorities. "
                  "Name what you use the phone for, such as photos, games or battery life, or pick an example.")
    raw = f'{{"needs": {parsed.needs}, "budget": {parsed.budget}, "must_have": {parsed.must_have}}}'
    return parsed, raw, "keyword", notice


def template_explanation(build, need):
    ranked = sorted(DIMS, key=lambda d: -need.get(d, 0))
    weakest = min(DIMS, key=lambda d: build.config.vec[d])
    if need[ranked[0]] == need[ranked[-1]]:
        opening = "No priority stands out, so this is a general build"
    else:
        opening = f"This build puts {DIM_LABELS[ranked[0]].lower()} and {DIM_LABELS[ranked[1]].lower()} first"
    return (f"{opening}, "
            f"at ₹{build.config.price:,} and {round(build.config.mass)} g, with about "
            f"{build.config.hours:.1f} hours of mixed use. It gives up the most on "
            f"{DIM_LABELS[weakest].lower()}.")


def image_tag(fig, width):
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=100, facecolor=fig.get_facecolor())
    encoded = b64encode(buffer.getvalue()).decode("ascii")
    return f'<img src="data:image/png;base64,{encoded}" style="width:{width}px;max-width:100%;height:auto">'


def build_card(text, need, budget, must_have, option, status, raw="", notice=None, written=None):
    \"\"\"The result as one HTML block with its own colours, so it reads the same in Colab's dark mode.\"\"\"
    builds, stats = recommend(need, budget, must_have)
    parts = [f'<p style="margin:0 0 6px"><b>Request:</b> {escape(text)}</p>',
             f'<p style="margin:0 0 12px;font-size:13px">{escape(status)}</p>']
    if notice:
        parts.append(f'<p style="margin:0 0 12px;padding:10px;background:#FFE7A8">{escape(notice)}</p>')
    if not builds:
        cheapest = cheapest_possible()
        message = (f"No build fits ₹{budget:,}. The cheapest possible phone costs ₹{cheapest:,}."
                   if budget and budget < cheapest else
                   "No build meets these requirements on one frame. Remove a required module or raise the budget.")
        parts.append(f'<p style="padding:10px;background:#FFE7A8">{message}</p>')
    else:
        build = builds[min(option, len(builds) - 1)]
        cell = "padding:4px 16px 4px 0;text-align:left"
        rows = "".join(f'<tr><td style="{cell}">{escape(p.mod.name)}</td><td style="{cell}">{CATEGORY_LABELS[p.mod.cat]}</td>'
                       f'<td style="{cell}">₹{p.mod.price:,}</td>'
                       f'<td style="{cell}">{escape(PLACEMENT_RULES.get(p.mod.cat, "Any free slot"))}</td></tr>'
                       for p in build.placed)
        parts.append(
            '<div style="display:flex;flex-wrap:wrap;gap:24px;align-items:flex-start">'
            f"<div>{image_tag(phone_figure(build, need), 230)}"
            '<p style="font-size:12px;margin:6px 0 0">Yellow modules serve your top priority.</p></div>'
            '<div style="flex:1;min-width:300px">'
            f'<p style="margin:0 0 10px"><b>₹{build.config.price:,}</b> &nbsp; <b>{round(build.config.mass)} g</b> &nbsp; '
            f"<b>{build.config.hours:.1f} h</b> mixed use &nbsp; match <b>{build.score:.2f}</b></p>"
            f"{image_tag(vector_figure(need, build), 560)}"
            '<p style="font-size:12px;margin:4px 0 10px">Dark bar: what this build delivers. '
            "Yellow mark: what you need.</p>"
            f'<p style="margin:0 0 8px">{escape(written or template_explanation(build, need))}</p>'
            f'<p style="font-size:12px;margin:0">Searched {stats["possible"]:,} combinations. '
            f'{stats["fit_frame"]:,} fit the frame, and {stats["feasible"]:,} meet your limits.</p></div></div>'
            f'<table style="margin-top:14px;border-collapse:collapse;font-size:13px;color:#2F4A47;background:#E8EBE6">'
            f'<tr><th style="{cell}">Module</th><th style="{cell}">Type</th><th style="{cell}">Price</th>'
            f'<th style="{cell}">Placement</th></tr>{rows}</table>')
    if raw:
        parts.append('<details style="margin-top:12px"><summary>See what the model returned</summary>'
                     f'<pre style="white-space:pre-wrap;font-size:12px;color:#2F4A47;background:#D3D8D1;padding:10px">'
                     f"{escape(raw)}</pre></details>")
    return ('<div style="background:#E8EBE6;color:#2F4A47;padding:20px;border-radius:6px;'
            f'font-family:Barlow,Arial,sans-serif;max-width:960px">{"".join(parts)}</div>')


def show_request(text, person=None):
    parsed, raw, source, notice = read_request(text, person)
    written = None
    if source == "live":
        builds, _ = recommend(parsed.needs, parsed.budget, parsed.must_have)
        try:
            written = complete(explain(text, builds[0], parsed.needs)).strip() if builds else None
        except LLMError:
            written = None
    display(HTML(build_card(text, parsed.needs, parsed.budget, tuple(parsed.must_have), 0, SOURCE_TEXT[source],
                            raw, notice, written)))
"""

WORKED = """examples = presets()
for name in ("Wedding photographer", "Trek guide", "Hinglish gamer"):
    show_request(examples[name]["text"], examples[name])
"""

TYPED = """show_request("I shoot videos for YouTube and edit on the phone, need lots of storage, around 60k.")
show_request("I fix wind turbines and climb towers in storms.")
"""

UI = """TYPE_OWN = "Type my own"
examples = presets()
first = next(iter(examples.values()))

prompt_box = widgets.Textarea(value=first["text"], layout=widgets.Layout(width="100%", height="90px"))
example_picker = widgets.Dropdown(options=[TYPE_OWN, *examples], value=first["name"], description="Examples")
build_button = widgets.Button(description="Build my phone", button_style="primary")
option_picker = widgets.ToggleButtons(options=["Best", "Second", "Third"])
sliders = {d: widgets.FloatSlider(value=0.1, min=0, max=1, step=0.05, description=DIM_LABELS[d],
                                  continuous_update=False) for d in DIMS}
budget_box = widgets.BoundedIntText(value=0, min=0, max=500000, step=1000, description="Budget ₹")
must_box = widgets.SelectMultiple(options=[(m.name, m.id) for m in MODULES], description="Must have", rows=6)
view = widgets.Output()
ui = {"updating": False, "html": ""}


def refresh(_=None):
    if ui["updating"]:
        return
    need = {d: sliders[d].value for d in DIMS}
    edited = any(abs(need[d] - ui["parsed_needs"][d]) > 1e-6 for d in DIMS)
    status = "Priorities changed by hand." if edited else SOURCE_TEXT[ui["source"]]
    ui["html"] = build_card(ui["text"], need, budget_box.value or None, tuple(must_box.value),
                            ["Best", "Second", "Third"].index(option_picker.value), status, ui["raw"], ui["notice"])
    with view:
        view.clear_output(wait=True)
        display(HTML(ui["html"]))


def run_request(_=None):
    text = prompt_box.value.strip()
    if not text:
        return
    person = next((p for p in examples.values() if p["text"] == text), None)
    parsed, raw, source, notice = read_request(text, person)
    ui.update(updating=True, text=text, raw=raw, source=source, notice=notice, parsed_needs=dict(parsed.needs))
    for d in DIMS:
        sliders[d].value = parsed.needs[d]
    budget_box.value = parsed.budget or 0
    must_box.value = tuple(parsed.must_have)
    option_picker.value = "Best"
    example_picker.value = person["name"] if person else TYPE_OWN
    ui["updating"] = False
    refresh()


def pick_example(change):
    if not ui["updating"] and change["new"] != TYPE_OWN:
        prompt_box.value = examples[change["new"]]["text"]
        run_request()


example_picker.observe(pick_example, names="value")
build_button.on_click(run_request)
for control in (*sliders.values(), budget_box, must_box, option_picker):
    control.observe(refresh, names="value")

priorities = widgets.Accordion(children=[widgets.VBox([*sliders.values(), budget_box, must_box])], selected_index=None)
priorities.set_title(0, "Change the priorities")
display(widgets.VBox([prompt_box, widgets.HBox([example_picker, build_button]), priorities, option_picker, view]))
run_request()
"""

TEST_CELL = """# Throwaway checks, only in the --test run.
FONT.insert(0, "NoSuchFont")
assert "saved Claude reply" in ui["html"] and "1-inch" in ui["html"], "first load"
example_picker.value = "Trek guide"
assert "Satellite + long-range" in ui["html"] and "Rugged armour" in ui["html"], "example"
sliders["camera"].value = 1.0
assert "changed by hand" in ui["html"], "slider"
option_picker.value = "Second"
second = ui["html"]
option_picker.value = "Third"
assert second != ui["html"], "option"
prompt_box.value = "I fix wind turbines and climb towers in storms."
build_button.click()
assert "no words it knows" in ui["html"] and example_picker.value == TYPE_OWN, "keyword notice"
assert "No priority stands out" in ui["html"], "tie"
budget_box.value = 5000
assert "cheapest possible" in ui["html"], "budget"
budget_box.value = 0
print("WIDGET CHECKS PASSED", sys.version.split()[0], widgets.__version__, np.__version__, pd.__version__)
"""

engine_md = ("## 2. Vector search and placement\n\nThe need and every candidate phone sit in the same nine-axis space. "
             "Hard limits filter first: frame space, budget, dependencies and required modules. "
             "The rest are ranked by `0.5 × cosine + 0.5 × attainment − 0.2 × price ÷ ₹90,000`, "
             "then a depth-first search places the modules using heat, antenna, grip and balance costs.")

cells = [
    new_markdown_cell(
        "# Modula: AI-assisted configuration of modular smartphones\n\n"
        "Aditi R Sankpal, Diya S Ellur, Mahiyu Dasgupta, Nidhi K, Rajat L Harihar\n\n"
        "A person describes how they use a phone. Claude turns that into a nine-axis need vector, and a constrained "
        "search picks the modules and places them on the frame. Claude never chooses hardware: Python enforces "
        "budget, space, dependencies and placement.\n\n"
        "**To run it:** choose *Runtime > Run all*. Nothing needs installing and no key is needed.\n\n"
        "**What runs here:** the search, placement, evaluation and tests all run live. Claude itself doesn't, because "
        "the Claude command line isn't available in Colab. Examples use recorded Claude replies, and typed requests "
        "use keyword matching. Each result says which one it used.\n\n"
        "Sections: 1 Catalogue, 2 Search, 3 Prompts, 4 Recorded data, 5 Keyword baseline, 6 Claude call, 7 Figures, "
        "8 Results, 9 Tests, 10 Worked examples, 11 Try it."),
    new_code_cell(SETUP),
    new_markdown_cell("## 1. Module catalogue\n\n23 modules on a 2 × 6 frame. Prices, masses and power figures are "
                      "illustrative design assumptions, not measured hardware."),
    new_code_cell(source("modula/catalogue.py")),
    new_markdown_cell(engine_md),
    new_code_cell(source("modula/engine.py")),
    new_markdown_cell("## 3. Prompts\n\nThree versions were compared: v1 is a minimal request, v2 adds a role, axis "
                      "definitions, an anchored scale and a strict schema, and v3 adds inference rules, a reasoning "
                      "step and few-shot examples. v3 is the production prompt. The explanation prompt only receives "
                      "computed facts, so it can't invent specs."),
    new_code_cell(source("modula/prompts.py")),
    new_markdown_cell("## 4. Personas and recorded replies\n\n8 tuning personas and 16 held-out test personas with "
                      "labelled needs, plus the 72 recorded Claude replies behind the results "
                      "(24 personas × 3 prompts). The personas are written, not real users."),
    new_code_cell(DATA_CELL, metadata={"cellView": "form"}),
    new_markdown_cell("## 5. Keyword baseline\n\nThe non-AI comparison, and the fallback when no model is reachable."),
    new_code_cell(source("modula/keyword_parser.py")),
    new_markdown_cell("## 6. Claude call\n\nCalls Claude through the Claude Code command line. On a computer without it, "
                      "`is_available()` returns False and the rest of the notebook carries on."),
    new_code_cell(source("modula/llm.py")),
    new_markdown_cell("## 7. Figures\n\nThe phone drawing and the need-versus-delivered chart."),
    new_code_cell(source("modula/figures.py")),
    new_markdown_cell("## 8. Results\n\nScores the recorded replies against the labels, then runs the engine on what "
                      "each method parsed. A failed build means no build at all, over budget, or missing a module the "
                      "person needs. Regret is the gap to what perfect parsing would have achieved."),
    new_code_cell(between((ROOT / "eval/score.py").read_text(encoding="utf-8"), "# A fixed mid-to-high", "def main(split):")),
    new_code_cell(EVAL),
    new_markdown_cell("Limits: the labels are ours, catalogue figures are illustrative and the personas are written, "
                      "not real users. The keyword list was written with these personas in view, which likely flatters it."),
    new_markdown_cell("## 9. Tests\n\nThese include the numbers on the Results slide, so changing a prompt or the "
                      "engine makes a test fail until the slide is updated."),
    new_code_cell(between((ROOT / "tests/test_modula.py").read_text(encoding="utf-8"), "def need(**values):", 'if __name__ == "__main__":')),
    new_code_cell(RUN_TESTS),
    new_markdown_cell("## 10. Worked examples\n\nThese three use recorded Claude replies. Neither \"satellite\" nor "
                      "\"armour\" appears in the trek guide's request, and \"garam nahi\" means the gamer's phone "
                      "shouldn't heat up."),
    new_code_cell(SHOW),
    new_code_cell(WORKED),
    new_markdown_cell("Without Claude, a typed request goes to keyword matching. The first request below uses words on "
                      "the list and gets a sensible build. The second uses none, and the result says so."),
    new_code_cell(TYPED),
    new_markdown_cell("## 11. Try it\n\nRun this cell, then pick an example or type a request and click "
                      "*Build my phone*. Open *Change the priorities* to adjust the sliders by hand."),
    new_code_cell(UI),
]

testing = "--test" in sys.argv
if testing:
    cells.append(new_code_cell(TEST_CELL))

nb = new_notebook(cells=cells)
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
NotebookClient(nb, timeout=300, kernel_name="python3").execute()

for number, cell in enumerate(c for c in nb.cells if c.cell_type == "code"):
    streams = [o.get("name") for o in cell.outputs if o.output_type == "stream"]
    assert "stderr" not in streams, f"code cell {number} wrote to stderr: {cell.outputs}"

if testing:
    print(next(o.text for o in nb.cells[-1].outputs if o.output_type == "stream").strip())
else:
    nb.cells[-1].outputs = []
    nb.cells[-1].execution_count = None

nb.metadata = {"kernelspec": {"name": "python3", "display_name": "Python 3"},
               "language_info": {"name": "python"},
               "colab": {"name": "Modula.ipynb", "provenance": [], "toc_visible": True}}
for cell in nb.cells:
    cell.metadata.pop("execution", None)

out = Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
nbformat.validate(nb)
nbformat.write(nb, out)
results = next(c for c in nb.cells if c.cell_type == "code" and c.source.startswith("summary, methods"))
print("".join(o.get("text", "") for o in results.outputs if o.output_type == "stream").strip())
print(results.outputs[0].data["text/plain"])
test_cell = next(c for c in nb.cells if c.cell_type == "code" and c.source.startswith("suite ="))
print("tests:", "".join(o.get("text", "") for o in test_cell.outputs if o.output_type == "stream").strip()[-60:])
worked = [c for c in nb.cells if c.cell_type == "code" and c.source.startswith(("examples = presets()\nfor", "show_request("))]
preview = "".join(o.data["text/html"] for c in worked for o in c.outputs if "text/html" in o.get("data", {}))
Path(sys.argv[1]).with_name("nb_preview.html").write_text(
    f'<!doctype html><meta charset="utf-8"><body style="background:#222;padding:16px">{preview}</body>', encoding="utf-8")
print("saved", out, out.stat().st_size, "bytes,", len(nb.cells), "cells")
