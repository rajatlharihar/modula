"""Runs each persona through prompts v1, v2 and v3 and saves the replies for scoring.
Replies already saved are skipped, so a stopped run continues where it left off.

Usage: py eval/collect.py dev|test
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modula import llm
from modula.data import REPLY_DIR, load_personas, reply_path
from modula.prompts import PROMPTS


def main(split):
    REPLY_DIR.mkdir(parents=True, exist_ok=True)
    for version, prompt in PROMPTS.items():
        for person in load_personas()[split]:
            path = reply_path(split, version, person["id"])
            if path.exists():
                continue
            reply = llm.complete(prompt(person["text"]))
            record = {"split": split, "version": version, "id": person["id"], "reply": reply}
            path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"saved {path.name}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dev")
