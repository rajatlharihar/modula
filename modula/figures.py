"""The phone drawing and the need-versus-delivered chart, both in matplotlib."""
try:
    from matplotlib.figure import Figure
    from matplotlib.patches import Circle, FancyBboxPatch, Rectangle
except ImportError:  # the web build has no matplotlib, only top_categories is used
    Figure = Circle = FancyBboxPatch = Rectangle = None

from .catalogue import CATEGORY_LABELS, DIM_LABELS, DIMS, GRID_COLS, GRID_ROWS

INK = "#10131C"       # phone body, text
SLATE = "#2A2F3D"     # ordinary modules
LINE = "#D5D8DF"
PAPER = "#F1F2F4"     # page background
CARD = "#F8F9FA"
COBALT = "#0047AB"    # the accent, as on the slides
COBALT_L = "#DCE6F6"
FREE = "#5A6178"
PINE, SAGE, MARIGOLD = INK, SLATE, COBALT  # old names kept for any importers

from pathlib import Path

try:
    from matplotlib import font_manager

    for _f in (Path(__file__).resolve().parent.parent / "static").glob("Outfit-*.ttf"):
        font_manager.fontManager.addfont(str(_f))
except ImportError:
    pass
FONT = ["Outfit", "Segoe UI", "DejaVu Sans"]

# Which module categories serve each axis. Portability is a property of the whole phone.
SERVES = {
    "camera": {"camera", "aux"}, "performance": {"compute", "cooling"}, "battery": {"battery"},
    "audio": {"audio"}, "storage": {"storage"}, "connectivity": {"net"},
    "durability": {"armour"}, "sensing": {"sensor"}, "portability": set(),
}

CELL_W, CELL_H, GAP, PAD = 1.42, 0.86, 0.07, 0.24


def _rounded(x, y, w, h, radius, **style):
    return FancyBboxPatch((x + radius, y + radius), w - 2 * radius, h - 2 * radius,
                          boxstyle=f"round,pad={radius},rounding_size={radius}", **style)


def top_categories(need):
    """Categories serving what this person cares about most. They get the bright colour."""
    highest = max(need.get(d, 0) for d in DIMS)
    if highest - min(need.get(d, 0) for d in DIMS) < 1e-9:
        return set()
    return set().union(*(SERVES[d] for d in DIMS if need.get(d, 0) >= highest - 1e-9))


def phone_figure(build, need):
    """The back of the phone, seen from behind, with the camera at the top."""
    width = GRID_COLS * CELL_W + (GRID_COLS - 1) * GAP + 2 * PAD
    height = GRID_ROWS * CELL_H + (GRID_ROWS - 1) * GAP + 2 * PAD
    fig = Figure(figsize=(width, height), dpi=200, facecolor=PAPER)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, width)
    ax.set_ylim(height, 0)
    ax.axis("off")
    ax.add_patch(_rounded(0, 0, width, height, 0.3, facecolor=INK, edgecolor="none"))

    def cell_box(x, y, w, h):
        left = PAD + x * (CELL_W + GAP)
        top = PAD + y * (CELL_H + GAP)
        return left, top, w * CELL_W + (w - 1) * GAP, h * CELL_H + (h - 1) * GAP

    occupied = set()
    placed = build.placed if build else ()
    for p in placed:
        occupied |= {(c, r) for c in range(p.x, p.x + p.w) for r in range(p.y, p.y + p.h)}

    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            if (c, r) in occupied:
                continue
            left, top, w, h = cell_box(c, r, 1, 1)
            ax.add_patch(_rounded(left, top, w, h, 0.07, facecolor="none", edgecolor=FREE,
                                  linewidth=1.0, linestyle=(0, (3, 3)), alpha=0.9))
            ax.text(left + w / 2, top + h / 2, "Free", color=FREE, alpha=1, fontsize=9,
                    ha="center", va="center", family=FONT)

    bright = top_categories(need)
    for p in placed:
        left, top, w, h = cell_box(p.x, p.y, p.w, p.h)
        fill = COBALT if p.mod.cat in bright else SLATE
        ax.add_patch(_rounded(left, top, w, h, 0.07, facecolor=fill, edgecolor="none"))
        if p.mod.cat in ("camera", "aux"):
            radius = min(w, h) * 0.2
            ax.add_patch(Circle((left + w - radius - 0.13, top + radius + 0.13), radius,
                                facecolor=INK, edgecolor="#C9CED9", linewidth=1.2))
            ax.add_patch(Circle((left + w - radius - 0.13, top + radius + 0.13), radius * 0.45,
                                facecolor="#151926", edgecolor="none"))
        ax.text(left + 0.11, top + 0.1, p.mod.short, color="white", fontsize=11, fontweight="semibold",
                ha="left", va="top", family=FONT)
        ax.text(left + 0.11, top + h - 0.1, CATEGORY_LABELS[p.mod.cat], color="#B8C3DD", fontsize=8.5,
                ha="left", va="bottom", family=FONT)
    return fig


def vector_figure(need, build):
    """One row per axis: the bar is what the phone delivers, the mark is what the person needs."""
    fig = Figure(figsize=(6.2, 3.3), dpi=200, facecolor=PAPER)
    ax = fig.add_axes([0.2, 0.09, 0.78, 0.9])
    ax.set_facecolor(PAPER)
    ax.set_xlim(0, 1)
    ax.set_ylim(len(DIMS) - 0.4, -0.6)
    for i, d in enumerate(DIMS):
        ax.add_patch(Rectangle((0, i - 0.3), 1, 0.6, facecolor=COBALT_L, edgecolor="none"))
        if build:
            ax.add_patch(Rectangle((0, i - 0.3), build.config.vec[d], 0.6, facecolor=COBALT, edgecolor="none"))
        n = need.get(d, 0)
        ax.add_patch(Rectangle((n - 0.007, i - 0.44), 0.014, 0.88, facecolor=INK,
                               edgecolor=PAPER, linewidth=0.4, zorder=3))
        ax.text(-0.02, i, DIM_LABELS[d], color=INK, fontsize=9.5, ha="right", va="center", family=FONT)
    ax.set_xticks([0, 0.5, 1])
    ax.set_xticklabels(["0", "0.5", "1"], fontsize=8, color=INK, family=FONT)
    ax.set_yticks([])
    ax.tick_params(axis="x", length=0, pad=3)
    for spine in ax.spines.values():
        spine.set_visible(False)
    return fig
