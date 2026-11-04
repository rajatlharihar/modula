"""Non-AI baseline: keyword matching. The evaluation compares the LLM against it,
and the demo falls back to it when no model is reachable.
"""
import re

from .catalogue import DIMS
from .prompts import ParsedReply

KEYWORDS = {
    "camera": ("camera", "photo", "photograph", "video", "vlog", "film", "shoot", "zoom", "picture", "creator"),
    "performance": ("game", "gaming", "bgmi", "genshin", "cod", "fast", "lag", "edit", "performance", "speed"),
    "battery": ("battery", "charge", "all day", "long lasting", "lasts", "hour", "shift", "power"),
    "audio": ("music", "audio", "speaker", "sound", "flac", "audiophile", "podcast", "loud", "netflix", "youtube"),
    "storage": ("storage", "space", "library", "raw", "backup", "files", "collection", "tb", "gb"),
    "connectivity": ("5g", "network", "signal", "coverage", "satellite", "internet", "data", "wifi", "stream"),
    "durability": ("rugged", "drop", "tough", "break", "dust", "rain", "mud", "water", "rocks", "strong"),
    "sensing": ("health", "heart", "ecg", "oxygen", "vitals", "sensor", "thermal", "air"),
    "portability": ("light", "small", "compact", "thin", "weight", "pocket", "portable"),
}

MODULE_KEYWORDS = {
    "net-sat": ("satellite", "no signal", "no network", "no coverage", "off-grid"),
    "net-mm": ("mmwave", "fastest data"),
    "sen-health": ("ecg", "heart", "oxygen", "vitals"),
    "sen-env": ("air quality", "thermal", "heat sensor"),
    "aux-tele": ("telephoto", "long zoom", "periscope"),
    "cool-vc": ("overheat", "cooling", "garam"),
}


def parse_budget(text):
    t = text.lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac)", t)
    if match:
        return round(float(match.group(1)) * 100000)
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:k\b|hazaar|thousand)", t)
    if match:
        return round(float(match.group(1)) * 1000)
    match = re.search(r"(?:₹|rs\.?\s*|budget\D{0,12}|under\s+|max\s+)(\d{4,7})", t)
    if match:
        return int(match.group(1))
    return None


def keyword_parse(text):
    t = f" {text.lower()} "
    needs = {}
    for d in DIMS:
        hits = sum(k in t for k in KEYWORDS[d])
        needs[d] = 1.0 if hits >= 2 else 0.7 if hits == 1 else 0.1
    must_have = [i for i, words in MODULE_KEYWORDS.items() if any(w in t for w in words)]
    return ParsedReply(True, True, True, needs, parse_budget(text), must_have, "")


def found_nothing(parsed):
    """True when no keyword matched, so the needs are only the flat default."""
    return not parsed.must_have and all(v == 0.1 for v in parsed.needs.values())
