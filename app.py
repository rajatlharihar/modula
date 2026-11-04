"""Modula demo. Run with: py -m streamlit run app.py"""
import pandas as pd
import streamlit as st

from modula.sku import workbook_bytes
from modula.template import template_explanation
from modula import engine, figures, llm
from modula.catalogue import CATEGORY_LABELS, DIM_LABELS, DIMS, MODULE_BY_ID, PLACEMENT_RULES
from modula.data import load_personas, load_reply
from modula.keyword_parser import found_nothing, keyword_parse
from modula.prompts import PROMPTS, explain, parse_model_reply

PRESET_IDS = ("d1", "d4", "t15", "d5", "d7", "d2")

st.set_page_config(page_title="Modula", layout="wide")

STYLE = """
<style>
@font-face{font-family:"Restora";src:url(/app/static/RestoraItalic.ttf);font-style:italic}
@font-face{font-family:"Typewriter";src:url(/app/static/typewriter.ttf)}
:root{--cobalt:#0047AB;--ink:#10131C;--grey:#8C919E;--line:#D5D8DF;--card:#F8F9FA}
html,body,.stApp,[data-testid="stMarkdownContainer"],textarea,input,button,summary{font-family:"Outfit",sans-serif}
[data-testid="stIconMaterial"],span[class*="material"]{font-family:"Material Symbols Rounded"!important;font-size:24px!important;letter-spacing:0!important;text-transform:none!important}
.block-container{padding-top:2.2rem;max-width:1500px}
header[data-testid="stHeader"]{background:transparent}
h1{font-family:"Restora",serif!important;font-style:italic;font-weight:400!important;font-size:96px!important;line-height:1!important;letter-spacing:-1.5px;color:var(--ink);padding:0!important}
h1:before{content:"Prompt Engineering and Generative AI";display:block;font-family:"Typewriter",monospace;font-style:normal;font-size:16px;letter-spacing:.14em;text-transform:uppercase;color:var(--grey);margin-bottom:14px}
[data-testid="stMarkdownContainer"] p{font-size:20px;line-height:1.4}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{font-family:"Typewriter",monospace!important;font-size:14px!important;letter-spacing:.06em;color:var(--grey)!important;line-height:1.5}
label p,[data-testid="stWidgetLabel"] p{font-family:"Typewriter",monospace!important;font-size:15px!important;letter-spacing:.12em;text-transform:uppercase;color:var(--grey)}
textarea,input{border-radius:20px!important;background:var(--card)!important;border:1.5px solid var(--line)!important;font-size:20px!important}
.stButton>button,.stDownloadButton>button{border-radius:999px;font-size:18px;font-weight:500;padding:.55rem 1.4rem;border:1.5px solid var(--ink);background:transparent;color:var(--ink)}
.stButton>button[kind="primary"]{background:var(--cobalt);border-color:var(--cobalt);color:#fff}
.stButton>button:hover,.stDownloadButton>button:hover{border-color:var(--cobalt);color:var(--cobalt)}
.stButton>button[kind="primary"]:hover{background:#00306F;color:#fff}
[data-testid="stExpander"]{background:var(--card);border:1.5px solid var(--line);border-radius:24px}
[data-testid="stExpander"] summary p{font-size:20px;font-weight:500}
[data-testid="stPills"] button,[data-testid="stSegmentedControl"] button{border-radius:999px;font-size:17px}
table{border-collapse:collapse;width:100%}
th{font-family:"Typewriter",monospace!important;font-weight:400!important;font-size:14px!important;letter-spacing:.12em;text-transform:uppercase;color:var(--grey)!important;border-bottom:1.5px solid var(--ink)!important}
td{font-size:26px!important;color:var(--ink);border-bottom:1.5px solid var(--line)!important}
td strong{font-weight:600}
[data-testid="stImage"] img,[data-testid="stPyplot"] img{border-radius:28px}
[data-testid="stAlert"]{border-radius:20px}
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)


@st.cache_data
def presets():
    data = load_personas()
    people = {p["id"]: {**p, "split": split} for split in ("dev", "test") for p in data[split]}
    return {people[i]["name"]: people[i] for i in PRESET_IDS}


@st.cache_data(ttl=60)
def claude_connected():
    return llm.is_available()


def saved_reply(person):
    record = load_reply(person["split"], "v3", person["id"]) if person else None
    return record["reply"] if record else None


def read_request(text, person):
    """Claude first. Without it, a saved reply for an example, or keyword matching."""
    notice = None
    if claude_connected():
        try:
            raw = llm.complete(PROMPTS["v3"](text))
            parsed = parse_model_reply(raw)
            if parsed.ok:
                return parsed, raw, "live", None
            notice = "Claude replied, but not in the expected format. Keyword matching ran instead."
        except llm.LLMError as error:
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


def apply_request(text, parsed, raw, source):
    """Sets the priority sliders, budget and required modules from a parsed request."""
    state = st.session_state
    state.update(text=text, raw=raw, source=source, reasoning=parsed.reasoning,
                 parsed_needs=dict(parsed.needs), explanation=None)
    state["budget"] = parsed.budget
    state["must"] = [MODULE_BY_ID[i].name for i in parsed.must_have]
    state["option"] = "Best"
    for d in DIMS:
        state[f"need_{d}"] = float(parsed.needs[d])


def choose_example():
    name = st.session_state.get("example")
    if name:
        st.session_state["prompt"] = presets()[name]["text"]
        st.session_state["run_now"] = name


def sync_example():
    """Typing your own request clears the highlighted example."""
    text = st.session_state.get("prompt", "").strip()
    if not any(p["text"] == text for p in presets().values()):
        st.session_state["example"] = None


# ---- First load: open on a worked example, with no model call ----

if "text" not in st.session_state:
    first = next(iter(presets().values()))
    st.session_state["prompt"] = first["text"]
    st.session_state["example"] = first["name"]
    reply = saved_reply(first)
    parsed_first = parse_model_reply(reply) if reply else keyword_parse(first["text"])
    apply_request(first["text"], parsed_first, reply or "", "saved" if reply else "keyword")

st.title("Modula")
st.write("Describe how you use a phone. Modula picks the modules and places them on the frame.")

left, middle, right = st.columns([1, 0.8, 1.3], gap="large")

# ---- Left: the request ----

with left:
    st.text_area("How do you use your phone?", key="prompt", height=120, on_change=sync_example)
    st.pills("Examples", list(presets()), key="example", on_change=choose_example)
    clicked = st.button("Build my phone", type="primary", width="stretch")
    example_to_run = st.session_state.pop("run_now", None)
    new_request = False

    if clicked or example_to_run:
        text = st.session_state["prompt"].strip()
        if text:
            person = next((p for p in presets().values() if p["text"] == text), None)
            with st.spinner("Reading your request"):
                parsed, raw, source, notice = read_request(text, person)
            apply_request(text, parsed, raw, source)
            new_request = True
            if notice:
                st.warning(notice)

    status = st.empty()
    with st.expander("See what the model returned"):
        st.code(st.session_state["raw"] or "No model output yet.", language="json", wrap_lines=True)

# ---- Right: priorities first, because everything else depends on them ----

with right:
    metrics = st.container()
    chart = st.container()
    message = st.container()
    with st.expander("Change the priorities", expanded=False):
        grid = st.columns(3)
        for i, d in enumerate(DIMS):
            with grid[i % 3]:
                st.slider(DIM_LABELS[d], 0.0, 1.0, step=0.05, key=f"need_{d}")
        st.number_input("Budget in rupees", min_value=0, step=1000, value=None, key="budget",
                        placeholder="No limit")
        st.multiselect("Modules the phone must include", [m.name for m in MODULE_BY_ID.values()], key="must")

need = {d: st.session_state[f"need_{d}"] for d in DIMS}
budget = st.session_state["budget"]
name_to_id = {m.name: m.id for m in MODULE_BY_ID.values()}
must_have = tuple(name_to_id[n] for n in st.session_state["must"])
builds, stats = engine.recommend(need, budget, must_have)

edited = any(abs(need[d] - st.session_state["parsed_needs"][d]) > 1e-6 for d in DIMS)
SOURCE_TEXT = {
    "live": "Read by Claude.",
    "saved": "Using a saved Claude reply. Claude isn't connected on this computer.",
    "keyword": "Read by keyword matching, no AI. Claude isn't connected on this computer.",
}
status.caption("Priorities changed by hand." if edited else SOURCE_TEXT[st.session_state["source"]])

# ---- Middle: the phone ----

with middle:
    labels = ["Best", "Second", "Third"][:len(builds)]
    if st.session_state.get("option") not in labels:
        st.session_state["option"] = labels[0] if labels else None
    choice = st.segmented_control("Build", labels, key="option", label_visibility="collapsed") if labels else None
    index = labels.index(choice) if choice in labels else 0
    build = builds[index] if builds else None
    st.pyplot(figures.phone_figure(build, need), clear_figure=True)
    if build and max(need.values()) > min(need.values()):
        st.caption("Blue modules serve your top priority.")

# ---- Right column contents ----

with middle:
    if build:
        label = f"{st.session_state.get('example') or 'Custom request'} ({labels[index]})"
        st.download_button("Download SKU sheet", workbook_bytes([(label, labels[index], build)]),
                           file_name="Modula-SKU.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           width="stretch")

with metrics:
    if build:
        st.markdown("| Price | Weight | Mixed use | Match |\n|:--|:--|:--|:--|\n"
                    f"| **₹{build.config.price:,}** | **{round(build.config.mass)} g** "
                    f"| **{build.config.hours:.1f} h** | **{build.score:.2f}** |")

with chart:
    st.pyplot(figures.vector_figure(need, build), clear_figure=True)
    st.caption("Blue bar: what this build delivers. Dark mark: what you need.")

with message:
    if not build:
        cheapest = engine.cheapest_possible()
        if budget and budget < cheapest:
            st.warning(f"No build fits ₹{budget:,}. The cheapest possible phone costs ₹{cheapest:,}.")
        else:
            st.warning("No build meets these requirements on one frame. "
                       "Remove a required module or raise the budget.")
    else:
        signature = (tuple(need.items()), budget, must_have, index)
        stored = st.session_state.get("explanation")
        if new_request and st.session_state["source"] == "live" and index == 0:
            try:
                with st.spinner("Writing the explanation"):
                    written = llm.complete(explain(st.session_state["text"], build, need)).strip()
                stored = {"signature": signature, "text": written}
                st.session_state["explanation"] = stored
            except llm.LLMError:
                stored = None
        if stored and stored["signature"] == signature:
            st.write(stored["text"])
        else:
            st.write(template_explanation(build, need))

        st.caption(f"Searched {stats['possible']:,} combinations. {stats['fit_frame']:,} fit the frame, "
                   f"and {stats['feasible']:,} meet your limits.")

with left:
    if build:
        with st.expander("See why each module is there"):
            rows = [{"Module": p.mod.name, "Type": CATEGORY_LABELS[p.mod.cat],
                     "Price": f"₹{p.mod.price:,}", "Placement": PLACEMENT_RULES.get(p.mod.cat, "Any free slot")}
                    for p in build.placed]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
