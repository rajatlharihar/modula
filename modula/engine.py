"""Vector scoring, exhaustive configuration search and module placement."""
import math
from dataclasses import dataclass
from functools import lru_cache
from itertools import product

import numpy as np

from .catalogue import (BASE_ATTRS, BASE_DRAW, BASE_MASS, BASE_PRICE, CATEGORIES, DIMS,
                        GRID_COLS, GRID_ROWS, INTERACTIONS, MODULE_BY_ID, MODULES)

# Normalisation anchors for the two axes that come from physics, not attributes.
FULL_ENDURANCE_HOURS = 16
MASS_LIGHTEST = 150
MASS_HEAVIEST = 330

# Score weights. ALPHA balances direction (cosine) against strength (attainment).
ALPHA = 0.5
COST_PENALTY = 0.20
MAX_PRICE = 90000

PLACEMENT_NODE_LIMIT = 40000


def clamp01(x):
    return max(0.0, min(1.0, x))


@dataclass(frozen=True)
class Config:
    vec: dict
    mass: float
    draw: float
    wh: float
    price: int
    hours: float


@dataclass(frozen=True)
class Placed:
    mod: object
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Build:
    mods: tuple
    config: Config
    score: float
    cos: float
    attainment: float
    placed: tuple
    placement_cost: float


def config_vector(mods):
    """Turns a list of modules into one vector in the shared 9-D space.

    Attributes stack with diminishing returns (noisy-OR), then interactions apply.
    Battery and portability are derived from watt-hours, total draw and total mass,
    so a heavier pack or a hungrier SoC changes them automatically.
    """
    miss = {d: 1 - BASE_ATTRS.get(d, 0) for d in DIMS}
    mass, draw, wh, price = BASE_MASS, BASE_DRAW, 0.0, BASE_PRICE
    ids = set()
    for m in mods:
        ids.add(m.id)
        mass += m.mass
        draw += m.draw
        price += m.price
        wh += m.wh
        for d, value in m.attrs.items():
            miss[d] *= 1 - value

    vec = {d: 1 - miss[d] for d in DIMS}
    for a, b, dim, delta in INTERACTIONS:
        if a in ids and b in ids:
            vec[dim] = clamp01(vec[dim] + delta)

    # Square root: going from 4h to 8h matters far more than going from 12h to 16h.
    hours = wh / draw if draw > 0 else 0.0
    vec["battery"] = math.sqrt(clamp01(hours / FULL_ENDURANCE_HOURS))
    vec["portability"] = clamp01(1 - (mass - MASS_LIGHTEST) / (MASS_HEAVIEST - MASS_LIGHTEST))
    return Config(vec, mass, draw, wh, price, hours)


def cosine(a, b):
    dot = na = nb = 0.0
    for d in DIMS:
        x, y = a.get(d, 0), b.get(d, 0)
        dot += x * y
        na += x * x
        nb += y * y
    return dot / math.sqrt(na * nb) if na and nb else 0.0


def fit_score(need, config):
    """Cosine rewards the right shape of phone but ignores how strong it is, and a weak
    phone can match perfectly in direction. Attainment fixes that by measuring how much
    capability the phone delivers on the axes this user weighted. Needs are squared so
    that a top priority outweighs several minor ones.
    """
    weighted = total = 0.0
    for d in DIMS:
        n = need.get(d, 0) ** 2
        weighted += n * config.vec[d]
        total += n
    attainment = weighted / total if total else 0.0
    cos = cosine(need, config.vec)
    score = ALPHA * cos + (1 - ALPHA) * attainment - COST_PENALTY * (config.price / MAX_PRICE)
    return score, cos, attainment


def _all_combinations():
    """Every legal choice: one module per category, or none where the category is optional."""
    options = []
    for cat, _, required in CATEGORIES:
        mods = [m for m in MODULES if m.cat == cat]
        options.append(mods if required else [None, *mods])
    capacity = GRID_COLS * GRID_ROWS
    out = []
    for choice in product(*options):
        mods = tuple(m for m in choice if m)
        if sum(m.w * m.h for m in mods) <= capacity:
            out.append(mods)
    return out


class _SearchTable:
    """All configurations as NumPy arrays, so ranking 16,000 phones takes milliseconds."""

    def __init__(self):
        self.combos = _all_combinations()
        self.configs = [config_vector(mods) for mods in self.combos]
        self.vectors = np.array([[c.vec[d] for d in DIMS] for c in self.configs])
        self.prices = np.array([c.price for c in self.configs], dtype=float)
        self.squared_norms = (self.vectors ** 2).sum(axis=1)
        index = {m.id: i for i, m in enumerate(MODULES)}
        self.module_index = index
        self.has = np.zeros((len(self.combos), len(MODULES)), dtype=bool)
        for row, mods in enumerate(self.combos):
            for m in mods:
                self.has[row, index[m.id]] = True
        self.deps_ok = np.array([_requirements_met(mods) for mods in self.combos])


def _requirements_met(mods):
    ids = {m.id for m in mods}
    return all(r in ids for m in mods for r in m.requires)


@lru_cache(maxsize=1)
def _table():
    return _SearchTable()


def possible_combinations():
    total = 1
    for cat, _, required in CATEGORIES:
        count = sum(m.cat == cat for m in MODULES)
        total *= count if required else count + 1
    return total


# ---- Placement: choose where each module sits on the 2 x 6 frame ----

def _within_camera_zone(mod, y, h):
    if mod.cat == "camera":
        return y + h <= 2
    if mod.cat == "aux":
        return y + h <= 3
    return True


def adjacent(a, b):
    overlaps_x = a.x < b.x + b.w and b.x < a.x + a.w
    overlaps_y = a.y < b.y + b.h and b.y < a.y + a.h
    return ((overlaps_x and (a.y + a.h == b.y or b.y + b.h == a.y)) or
            (overlaps_y and (a.x + a.w == b.x or b.x + b.w == a.x)))


def placement_cost(placed):
    """Soft ergonomic and thermal costs. Lower is better."""
    cost = 0.0
    mass_y = mass_total = 0.0
    by_cat = {}
    for p in placed:
        by_cat[p.mod.cat] = p
        mass_y += (p.y + p.h / 2) * p.mod.mass
        mass_total += p.mod.mass
        if p.mod.cat == "camera" and p.y != 0:
            cost += 4
        if p.mod.cat == "audio" and p.y + p.h != GRID_ROWS:
            cost += 3
        if p.mod.cat == "net" and p.y != 0 and p.y + p.h != GRID_ROWS:
            cost += 2
        if p.mod.cat == "sensor" and (p.y < 2 or p.y + p.h > 4):
            cost += 2

    compute, battery, cooling = by_cat.get("compute"), by_cat.get("battery"), by_cat.get("cooling")
    if compute and battery and adjacent(compute, battery):
        cost += 3
    if compute and cooling and not adjacent(compute, cooling):
        cost += 4
    if mass_total:
        cost += abs(mass_y / mass_total - GRID_ROWS / 2) * 0.5
    return cost


def _place_uncached(mods):
    """Depth-first search. Returns (placed, cost), or None when the modules can't physically fit."""
    def rank(m):
        return 0 if m.cat == "camera" else 1 if m.cat == "aux" else 2

    order = sorted(mods, key=lambda m: (rank(m), -m.w * m.h))
    grid = [[False] * GRID_COLS for _ in range(GRID_ROWS)]
    best, best_cost = None, math.inf
    nodes = 0

    def fits(x, y, w, h):
        if x + w > GRID_COLS or y + h > GRID_ROWS:
            return False
        return not any(grid[r][c] for r in range(y, y + h) for c in range(x, x + w))

    def mark(x, y, w, h, value):
        for r in range(y, y + h):
            for c in range(x, x + w):
                grid[r][c] = value

    def walk(i, placed):
        nonlocal best, best_cost, nodes
        nodes += 1
        if nodes > PLACEMENT_NODE_LIMIT:
            return
        if i == len(order):
            cost = placement_cost(placed)
            if cost < best_cost:
                best, best_cost = tuple(placed), cost
            return
        mod = order[i]
        shapes = [(mod.w, mod.h)] if mod.w == mod.h else [(mod.w, mod.h), (mod.h, mod.w)]
        for w, h in shapes:
            for y in range(GRID_ROWS):
                for x in range(GRID_COLS):
                    if not _within_camera_zone(mod, y, h) or not fits(x, y, w, h):
                        continue
                    mark(x, y, w, h, True)
                    placed.append(Placed(mod, x, y, w, h))
                    walk(i + 1, placed)
                    placed.pop()
                    mark(x, y, w, h, False)

    walk(0, [])
    return (best, best_cost) if best is not None else None


@lru_cache(maxsize=4096)
def _place_by_ids(ids):
    return _place_uncached([MODULE_BY_ID[i] for i in ids])


def place_modules(mods):
    return _place_by_ids(tuple(m.id for m in mods))


# ---- Recommendation ----

def _differs_enough(a, b):
    ids = {m.id for m in a}
    return sum(m.id not in ids for m in b) >= 2


def recommend(need, budget=None, must_have=(), top_n=3):
    """Hard constraints (cells, budget, dependencies, must-haves, placement) filter first.
    The survivors are ranked by fit score, and the best ones that can be physically placed
    are returned.
    """
    table = _table()
    n = np.array([need.get(d, 0) for d in DIMS], dtype=float)

    mask = table.deps_ok.copy()
    for module_id in must_have:
        if module_id in table.module_index:
            mask &= table.has[:, table.module_index[module_id]]
    if budget:
        mask &= table.prices <= budget

    feasible = np.flatnonzero(mask)
    stats = {"possible": possible_combinations(), "fit_frame": len(table.combos),
             "feasible": len(feasible), "placement_rejected": 0}
    if not len(feasible):
        return [], stats

    vectors = table.vectors[feasible]
    need_norm = float((n ** 2).sum())
    if need_norm:
        cos = (vectors @ n) / np.sqrt(table.squared_norms[feasible] * need_norm)
    else:
        cos = np.zeros(len(feasible))
    squared = n ** 2
    total = float(squared.sum())
    attainment = (vectors @ squared) / total if total else np.zeros(len(feasible))
    scores = ALPHA * cos + (1 - ALPHA) * attainment - COST_PENALTY * (table.prices[feasible] / MAX_PRICE)

    results = []
    for position in np.argsort(-scores, kind="stable"):
        if len(results) >= top_n:
            break
        row = feasible[position]
        mods = table.combos[row]
        if any(not _differs_enough(r.mods, mods) for r in results):
            continue
        placement = place_modules(mods)
        if placement is None:
            stats["placement_rejected"] += 1
            continue
        config = table.configs[row]
        score, cos_value, attainment_value = fit_score(need, config)
        results.append(Build(mods, config, score, cos_value, attainment_value, placement[0], placement[1]))
    return results, stats


def cheapest_possible():
    """The cheapest legal phone, used to explain an impossible budget."""
    return config_vector([MODULE_BY_ID[i] for i in ("c-eff", "b-3000", "cam-50")]).price
