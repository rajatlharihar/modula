"""The three prompt versions compared in the evaluation, plus the explanation prompt.
v3 is the production prompt used by the demo.
"""
import json
import math
from dataclasses import dataclass, field

from .catalogue import DIMS, MODULE_BY_ID, MODULES

AXES = ", ".join(DIMS)
MODULE_LIST = "; ".join(f"{m.id} ({m.name})" for m in MODULES)


def v1(text):
    """Zero-shot and minimal. This is what a first attempt looks like."""
    return f"""Read this description of what someone wants from their phone and rate how important each of these is to them from 0 to 1: {AXES}. Also give their budget if they mention one, and any specific modules they need.

Modules: {MODULE_LIST}

Reply with JSON containing "needs", "budget" and "must_have".

Description: {text}"""


_NEEDS_SCHEMA = ", ".join(f'"{d}": 0.0' for d in DIMS)
SCHEMA = f"""{{
  "reasoning": "one short sentence on what this person actually does with a phone",
  "needs": {{ {_NEEDS_SCHEMA} }},
  "budget": null,
  "must_have": []
}}"""

SYSTEM = f"""You are the requirements parser for a modular smartphone configurator. You convert a person's description of their life and phone use into a priority vector. A separate search engine uses that vector to choose hardware, so output data only.

AXES
- camera: photo and video quality
- performance: processing power for games, editing, heavy apps
- battery: hours between charges
- audio: speaker and headphone quality
- storage: on-device capacity
- connectivity: data speed and coverage, including places with no network
- durability: surviving drops, water, dust
- sensing: health and environmental sensors
- portability: low weight and small size

SCALE
1.0 = the main reason they are buying this phone
0.7 = clearly important to them
0.4 = useful, mentioned or implied in passing
0.1 = not mentioned, a normal person's baseline
0.0 = they explicitly said they do not care about it

MODULE IDS
{MODULE_LIST}

BUDGET
Give an integer in rupees, or null if none is stated. Read Indian number forms correctly: "60k" is 60000, "50 hazaar" is 50000, "1 lakh" and "1,00,000" are 100000."""


def v2(text):
    """Role, axis definitions, an anchored scale and a strict schema."""
    return f"""{SYSTEM}

MUST_HAVE
List module ids the person explicitly asked for.

OUTPUT
Return only this JSON, with no markdown fences and no extra text:
{SCHEMA}

DESCRIPTION
{text}"""


def v3(text):
    """v2 plus inference rules, an explicit reasoning step and few-shot examples."""
    return f"""{SYSTEM}

RULES
1. Infer needs from the person's life, not only their words. A job, hobby or place implies requirements.
2. Most axes should stay at 0.1. Rate an axis higher only with a reason. Don't give every axis a high score.
3. If they say they don't care about something, or say "nothing else matters", set those axes to 0.0.
4. Read Hindi and Hinglish the same way as English.
5. Fill "reasoning" first and base the scores on it.

MUST_HAVE
List a module id only if the person's need can't be met without that specific module:
- no network, off-grid or remote work -> net-sat
- needs the fastest possible data, or trading or streaming on 5G -> net-mm
- tracking heart, ECG, oxygen or vitals -> sen-health
- reading heat or air quality -> sen-env
- long zoom -> aux-tele
- must not overheat -> cool-vc
Otherwise leave the list empty, even when an axis scores high.

EXAMPLES
Description: Birdwatcher, I spend weekends in remote wetlands photographing small birds far away. About 40k.
{{"reasoning":"Distant wildlife photography in places with no coverage, on a modest budget.","needs":{{"camera":1.0,"performance":0.1,"battery":0.7,"audio":0.1,"storage":0.4,"connectivity":0.7,"durability":0.4,"sensing":0.1,"portability":0.4}},"budget":40000,"must_have":["aux-tele","net-sat"]}}

Description: Long-haul truck driver. Podcasts all day, calls with dispatch, phone rattles around the cab. Photos don't matter to me.
{{"reasoning":"Hours of audio and calls on the road in a rough environment, with no interest in photos.","needs":{{"camera":0.0,"performance":0.1,"battery":1.0,"audio":0.7,"storage":0.1,"connectivity":0.4,"durability":0.7,"sensing":0.1,"portability":0.1}},"budget":null,"must_have":[]}}

Description: Indie game developer testing builds on device, 1.2 lakh is fine.
{{"reasoning":"Runs demanding unoptimised game builds and keeps many large builds on the device.","needs":{{"camera":0.1,"performance":1.0,"battery":0.4,"audio":0.4,"storage":0.7,"connectivity":0.1,"durability":0.1,"sensing":0.1,"portability":0.1}},"budget":120000,"must_have":[]}}

OUTPUT
Return only this JSON, with no markdown fences and no extra text:
{SCHEMA}

DESCRIPTION
{text}"""


PROMPTS = {"v1": v1, "v2": v2, "v3": v3}


def explain(text, build, need):
    """Grounded explanation. The model gets computed facts and may only restate them,
    so it can't invent specs or claim a module that isn't in the build.
    """
    facts = {
        "modules": [m.name for m in build.mods],
        "price_inr": build.config.price,
        "weight_g": round(build.config.mass),
        "mixed_use_hours": round(build.config.hours, 1),
        "top_priorities": sorted(DIMS, key=lambda d: -need.get(d, 0))[:3],
    }
    return f"""You write one recommendation for a modular phone configurator.

What the person said: {text}

The search engine chose this build:
{json.dumps(facts, separators=(",", ":"))}

Write two plain sentences to this person. Say why this build suits them and name one trade-off it makes. Use only the facts given. Don't add specs, benchmarks or modules that aren't listed. No markdown, no bullet points, no greeting."""


@dataclass
class ParsedReply:
    ok: bool
    strict: bool = False  # the reply was already clean JSON
    schema_ok: bool = False
    needs: dict = field(default_factory=dict)
    budget: int | None = None
    must_have: list = field(default_factory=list)
    reasoning: str = ""


def _to_number(value):
    """Lenient number reading: null is 0, numeric strings count, anything else is NaN."""
    if value is None:
        return 0.0
    if isinstance(value, (bool, int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return 0.0
        try:
            return float(stripped)
        except ValueError:
            return math.nan
    return math.nan


def parse_model_reply(raw):
    """Pulls the JSON object out of a model reply and reports whether it was clean,
    since that is itself one of the things the evaluation measures.
    """
    text = str(raw).strip()
    strict, data = True, None
    try:
        data = json.loads(text)
    except ValueError:
        strict = False
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end + 1])
            except ValueError:
                data = None
    if not isinstance(data, dict) or not isinstance(data.get("needs"), (dict, list)):
        return ParsedReply(ok=False, strict=strict)

    # "needs" as a list is the wrong shape. It stays usable, with baseline values and schema_ok False.
    given = data["needs"] if isinstance(data["needs"], dict) else {}
    needs, schema_ok = {}, True
    for d in DIMS:
        value = _to_number(given[d]) if d in given else math.nan
        if math.isfinite(value):
            needs[d] = clamp_need(value)
        else:
            schema_ok = False
            needs[d] = 0.1

    budget_value = _to_number(data.get("budget"))
    budget = int(math.floor(budget_value + 0.5)) if math.isfinite(budget_value) and budget_value > 0 else None
    raw_must = data.get("must_have")
    must_have = [i for i in raw_must if i in MODULE_BY_ID] if isinstance(raw_must, list) else []
    return ParsedReply(True, strict, schema_ok, needs, budget, must_have, data.get("reasoning") or "")


def clamp_need(value):
    return max(0.0, min(1.0, value))
