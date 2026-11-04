"""JSON interface used by the web version (api/ on Vercel). Same engine as the Streamlit app."""
from . import engine
from .catalogue import (CATEGORY_LABELS, DIMS, DIM_LABELS, MODULES, MODULE_BY_ID, PLACEMENT_RULES)
from .data import load_personas, load_reply
from .keyword_parser import found_nothing, keyword_parse
from .prompts import parse_model_reply
from .template import template_explanation
from .figures import top_categories

PRESET_IDS = ("d1", "d4", "t15", "d5", "d7", "d2")


def _people():
    data = load_personas()
    return {p["id"]: {**p, "split": split} for split in ("dev", "test") for p in data[split]}


def presets():
    people = _people()
    return [{"id": i, "name": people[i]["name"], "text": people[i]["text"]} for i in PRESET_IDS]


def catalogue():
    return {
        "dims": [{"id": d, "label": DIM_LABELS[d]} for d in DIMS],
        "modules": [{"id": m.id, "name": m.name, "cat": m.cat, "category": CATEGORY_LABELS[m.cat]} for m in MODULES],
    }


def _serialize(build, need):
    bright = top_categories(need)
    return {
        "price": build.config.price,
        "mass": round(build.config.mass),
        "hours": round(build.config.hours, 1),
        "score": round(build.score, 2),
        "vec": {d: round(build.config.vec[d], 3) for d in DIMS},
        "explanation": template_explanation(build, need),
        "modules": [{
            "id": p.mod.id, "name": p.mod.name, "short": p.mod.short, "cat": p.mod.cat,
            "category": CATEGORY_LABELS[p.mod.cat], "price": p.mod.price,
            "x": p.x, "y": p.y, "w": p.w, "h": p.h, "bright": p.mod.cat in bright,
            "placement": PLACEMENT_RULES.get(p.mod.cat, "Any free slot"),
        } for p in build.placed],
    }


def parse_request(payload):
    """Returns (need, budget, must_ids, source, note)."""
    if payload.get("needs"):
        need = {d: float(payload["needs"].get(d, 0.1)) for d in DIMS}
        must = [m for m in payload.get("must", []) if m in MODULE_BY_ID]
        budget = payload.get("budget") or None
        return need, int(budget) if budget else None, must, "manual", "Priorities changed by hand."
    preset = payload.get("preset")
    if preset:
        person = _people().get(preset)
        if person:
            record = load_reply(person["split"], "v3", person["id"])
            parsed = parse_model_reply(record["reply"]) if record else keyword_parse(person["text"])
            source = "saved" if record else "keyword"
            note = ("Using a saved Claude reply. Claude isn't connected to this site."
                    if record else "Read by keyword matching, no AI.")
            return dict(parsed.needs), parsed.budget, list(parsed.must_have), source, note
    text = (payload.get("text") or "").strip()
    parsed = keyword_parse(text)
    note = "Read by keyword matching, no AI. Claude isn't connected to this site."
    if found_nothing(parsed):
        note = ("Keyword matching found nothing it knows. A language model would read this request, "
                "this site only has keyword matching.")
    return dict(parsed.needs), parsed.budget, list(parsed.must_have), "keyword", note


def build_response(payload):
    need, budget, must, source, note = parse_request(payload)
    builds, stats = engine.recommend(need, budget, tuple(must))
    out = {
        "need": {d: round(need[d], 2) for d in DIMS},
        "budget": budget, "must": must, "source": source, "note": note,
        "stats": stats,
        "builds": [_serialize(b, need) for b in builds],
    }
    if not builds:
        cheapest = engine.cheapest_possible()
        out["error"] = (f"No build fits ₹{budget:,}. The cheapest possible phone costs ₹{cheapest:,}."
                        if budget and budget < cheapest else
                        "No build meets these requirements on one frame. Remove a required module or raise the budget.")
    return out


def sku_bytes(payload):
    from .sku import workbook_bytes
    need, budget, must, source, note = parse_request(payload)
    builds, _ = engine.recommend(need, budget, tuple(must))
    index = int(payload.get("index", 0))
    labels = ["Best", "Second", "Third"]
    if not builds:
        return workbook_bytes()
    index = min(index, len(builds) - 1)
    name = payload.get("label") or "Custom request"
    return workbook_bytes([(name, labels[index], builds[index])])
