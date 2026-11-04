"""Scores recorded model replies against the hand-labelled ground truth.

Usage: py eval/score.py dev|test
"""
import json
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modula.catalogue import DIMS, MODULE_BY_ID
from modula.data import ROOT, load_personas, load_reply
from modula.engine import config_vector, cosine, fit_score, recommend
from modula.keyword_parser import keyword_parse
from modula.prompts import PROMPTS, parse_model_reply

# A fixed mid-to-high spec phone: what a non-modular, one-size-fits-all product gives everyone.
FIXED_PHONE = [MODULE_BY_ID[i] for i in ("c-pro", "b-4500", "cam-108", "aux-uw", "aud-st", "st-512", "net-mm")]


def full_need(needs):
    return {d: needs.get(d, 0.1) for d in DIMS}


def top_overlap(pred, gold, k=2):
    """Did the parser identify the axes this person cares about most?"""
    def top(v):
        return sorted(DIMS, key=lambda d: -v[d])[:k]
    return len(set(top(pred)) & set(top(gold))) / k


def grade_parse(parsed, person):
    gold = full_need(person["needs"])
    predicted, expected = set(parsed.must_have), set(person["mustHave"])
    return {
        "cosine": cosine(parsed.needs, gold),
        "top2": top_overlap(parsed.needs, gold),
        "budget_right": (parsed.budget or None) == (person["budget"] or None),
        "tp": len(predicted & expected),
        "fp": len(predicted - expected),
        "fn": len(expected - predicted),
    }


def grade_build(parsed, person, oracle):
    """Runs the engine on the parsed need, then scores what it chose against the true need.
    Regret is the gap to what perfect parsing would have achieved.
    """
    builds, _ = recommend(parsed.needs, parsed.budget, parsed.must_have, top_n=1)
    if not builds:
        return {"fit": 0.0, "regret": oracle, "over_budget": False,
                "missed_must": bool(person["mustHave"]), "none": True, "modules": []}
    build = builds[0]
    fit = fit_score(full_need(person["needs"]), build.config)[0]
    ids = [m.id for m in build.mods]
    return {
        "fit": fit, "regret": oracle - fit, "modules": ids, "price": build.config.price, "none": False,
        "over_budget": bool(person["budget"] and build.config.price > person["budget"]),
        "missed_must": any(i not in ids for i in person["mustHave"]),
    }


def summarise(rows):
    valid = [r for r in rows if r.get("parse")]
    tp = sum(r["parse"]["tp"] for r in valid)
    fp = sum(r["parse"]["fp"] for r in valid)
    fn = sum(r["parse"]["fn"] for r in valid)
    grades = [r["grade"] for r in rows]
    return {
        "n": len(rows),
        "strict_json": mean(r["strict"] for r in rows),
        "schema_valid": mean(r["schema_ok"] for r in rows),
        "need_cosine": mean(r["parse"]["cosine"] for r in valid) if valid else 0.0,
        "top2_recall": mean(r["parse"]["top2"] for r in valid) if valid else 0.0,
        "budget_accuracy": mean(r["parse"]["budget_right"] for r in valid) if valid else 0.0,
        "must_precision": tp / (tp + fp) if tp + fp else 1.0,
        "must_recall": tp / (tp + fn) if tp + fn else 1.0,
        "fit": mean(g["fit"] for g in grades),
        "regret": mean(g["regret"] for g in grades),
        "over_budget": sum(g["over_budget"] for g in grades),
        "missed_must": sum(g["missed_must"] for g in grades),
        "failed_builds": sum(g["none"] or g["over_budget"] or g["missed_must"] for g in grades),
    }


def evaluate(split):
    people = load_personas()[split]
    oracle = {}
    for p in people:
        builds, _ = recommend(full_need(p["needs"]), p["budget"], p["mustHave"], top_n=1)
        oracle[p["id"]] = fit_score(full_need(p["needs"]), builds[0].config)[0]

    methods = {}
    fixed = config_vector(FIXED_PHONE)
    methods["fixed"] = []
    for p in people:
        fit = fit_score(full_need(p["needs"]), fixed)[0]
        methods["fixed"].append({"id": p["id"], "strict": True, "schema_ok": True, "grade": {
            "fit": fit, "regret": oracle[p["id"]] - fit, "none": False,
            "modules": [m.id for m in FIXED_PHONE], "price": fixed.price,
            "over_budget": bool(p["budget"] and fixed.price > p["budget"]),
            "missed_must": any(i not in [m.id for m in FIXED_PHONE] for i in p["mustHave"]),
        }})

    methods["keyword"] = []
    for p in people:
        parsed = keyword_parse(p["text"])
        methods["keyword"].append({"id": p["id"], "strict": True, "schema_ok": True,
                                   "parse": grade_parse(parsed, p),
                                   "grade": grade_build(parsed, p, oracle[p["id"]])})

    for version in PROMPTS:
        rows = []
        for p in people:
            record = load_reply(split, version, p["id"])
            if not record:
                continue
            parsed = parse_model_reply(record["reply"])
            row = {"id": p["id"], "strict": parsed.strict, "schema_ok": parsed.schema_ok}
            if parsed.ok:
                row["parse"] = grade_parse(parsed, p)
                row["grade"] = grade_build(parsed, p, oracle[p["id"]])
            else:
                row["grade"] = {"fit": 0.0, "regret": oracle[p["id"]], "over_budget": False,
                                "missed_must": bool(p["mustHave"]), "none": True, "modules": []}
            rows.append(row)
        if rows:
            methods[version] = rows

    return {name: summarise(rows) for name, rows in methods.items()}, methods


def main(split):
    summary, methods = evaluate(split)
    out = ROOT / "eval" / "results"
    out.mkdir(exist_ok=True)
    (out / f"{split}.json").write_text(json.dumps({"summary": summary, "methods": methods}, indent=2), encoding="utf-8")

    print(f"\n{split} set\n")
    print(f"{'method':9} {'n':>3} {'JSON':>6} {'schema':>7} {'cosine':>7} {'top2':>6} {'budget':>7} "
          f"{'precis':>7} {'recall':>7} {'fit':>6} {'regret':>7} {'failed':>7}")
    for name, s in summary.items():
        print(f"{name:9} {s['n']:>3} {s['strict_json']:>6.0%} {s['schema_valid']:>7.0%} {s['need_cosine']:>7.3f} "
              f"{s['top2_recall']:>6.0%} {s['budget_accuracy']:>7.0%} {s['must_precision']:>7.0%} "
              f"{s['must_recall']:>7.0%} {s['fit']:>6.3f} {s['regret']:>7.3f} {s['failed_builds']:>7}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "test")
