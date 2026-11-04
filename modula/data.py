"""Loads the personas and the recorded model replies."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPLY_DIR = ROOT / "eval" / "replies"


def load_personas():
    return json.loads((ROOT / "eval" / "personas.json").read_text(encoding="utf-8"))


def reply_path(split, version, persona_id):
    return REPLY_DIR / f"{split}_{version}_{persona_id}.json"


def load_reply(split, version, persona_id):
    path = reply_path(split, version, persona_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
