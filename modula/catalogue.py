"""Module catalogue.

Prices, masses and power draws are illustrative design assumptions for this
concept, not measured values from real hardware.
"""
from dataclasses import dataclass, field

# The shared vector space. Module attributes, configurations and user needs
# are all expressed along these nine axes.
DIMS = ("camera", "performance", "battery", "audio", "storage",
        "connectivity", "durability", "sensing", "portability")

DIM_LABELS = {
    "camera": "Camera", "performance": "Performance", "battery": "Battery life",
    "audio": "Audio", "storage": "Storage", "connectivity": "Connectivity",
    "durability": "Durability", "sensing": "Sensing", "portability": "Portability",
}

# The frame: 2 columns by 6 rows of module cells, plus the display and shell.
GRID_COLS = 2
GRID_ROWS = 6

BASE_PRICE = 9000
BASE_MASS = 110
BASE_DRAW = 1.0
BASE_ATTRS = {"audio": 0.15, "storage": 0.15, "connectivity": 0.3, "durability": 0.2}


@dataclass(frozen=True)
class Module:
    id: str
    cat: str
    name: str
    short: str
    w: int  # width in grid cells
    h: int  # height in grid cells
    price: int
    mass: int
    draw: float  # average watts in mixed use
    attrs: dict = field(default_factory=dict, hash=False)
    wh: float = 0.0  # battery capacity
    requires: tuple = ()


# (id, label, required). Required categories must be present in every phone.
CATEGORIES = (
    ("compute", "Compute", True),
    ("battery", "Battery", True),
    ("camera", "Main camera", True),
    ("aux", "Second camera", False),
    ("audio", "Audio", False),
    ("storage", "Storage", False),
    ("net", "Connectivity", False),
    ("sensor", "Sensors", False),
    ("armour", "Protection", False),
    ("cooling", "Cooling", False),
)
CATEGORY_LABELS = {c[0]: c[1] for c in CATEGORIES}

MODULES = (
    Module("c-eff", "compute", "Efficiency SoC", "Efficiency SoC", 2, 1, 6000, 18, 0.7, {"performance": 0.45}),
    Module("c-bal", "compute", "Balanced SoC", "Balanced SoC", 2, 1, 11000, 20, 1.1, {"performance": 0.68}),
    Module("c-pro", "compute", "Flagship SoC", "Flagship SoC", 2, 1, 22000, 22, 1.6, {"performance": 0.88}),
    Module("c-game", "compute", "Overclocked gaming SoC", "Gaming SoC", 2, 1, 27000, 28, 2.1, {"performance": 0.97},
           requires=("cool-vc",)),

    Module("b-3000", "battery", "3,000 mAh pack", "3,000 mAh", 2, 1, 1800, 46, 0.0, {}, wh=11.6),
    Module("b-4500", "battery", "4,500 mAh pack", "4,500 mAh", 1, 3, 2500, 68, 0.0, {}, wh=17.4),
    Module("b-6000", "battery", "6,000 mAh pack", "6,000 mAh", 2, 2, 3400, 92, 0.0, {}, wh=23.2),
    Module("b-8000", "battery", "8,000 mAh pack", "8,000 mAh", 2, 3, 5000, 122, 0.0, {}, wh=31.0),

    Module("cam-50", "camera", "50 MP standard camera", "50 MP", 1, 1, 2500, 8, 0.1, {"camera": 0.45}),
    Module("cam-108", "camera", "108 MP wide camera", "108 MP", 2, 1, 6500, 14, 0.15, {"camera": 0.7}),
    Module("cam-1in", "camera", "1-inch pro sensor", "1-inch sensor", 2, 2, 14000, 30, 0.25, {"camera": 0.92}),

    Module("aux-uw", "aux", "Ultrawide + macro lens", "Ultrawide", 1, 1, 3000, 6, 0.05, {"camera": 0.2}),
    Module("aux-tele", "aux", "5x periscope telephoto", "5x tele", 2, 1, 7000, 14, 0.08, {"camera": 0.35}),

    Module("aud-st", "audio", "Stereo speaker module", "Stereo", 1, 1, 2000, 8, 0.1, {"audio": 0.5}),
    Module("aud-hifi", "audio", "Hi-Fi DAC + speakers", "Hi-Fi DAC", 2, 1, 6500, 12, 0.15, {"audio": 0.88}),

    Module("st-512", "storage", "512 GB storage", "512 GB", 1, 1, 3000, 3, 0.02, {"storage": 0.65}),
    Module("st-2tb", "storage", "2 TB storage", "2 TB", 1, 1, 9500, 5, 0.05, {"storage": 0.95}),

    Module("net-sat", "net", "Satellite + long-range radio", "Satellite", 1, 1, 5500, 7, 0.1, {"connectivity": 0.65}),
    Module("net-mm", "net", "mmWave 5G + Wi-Fi 7", "mmWave", 1, 1, 5000, 6, 0.2, {"connectivity": 0.72}),

    Module("sen-health", "sensor", "ECG, SpO2 + temperature", "Health", 1, 1, 4500, 5, 0.05, {"sensing": 0.72}),
    Module("sen-env", "sensor", "Thermal + air quality", "Thermal + air", 1, 1, 6000, 6, 0.05, {"sensing": 0.65}),

    Module("arm-rug", "armour", "Rugged armour spine", "Armour", 2, 1, 3500, 45, 0.0, {"durability": 0.75}),

    Module("cool-vc", "cooling", "Vapour chamber", "Cooling", 1, 1, 2500, 10, 0.0, {"performance": 0.08}),
)
MODULE_BY_ID = {m.id: m for m in MODULES}

# Pairwise relationships between modules: effects a per-module vector can't express.
# (module a, module b, axis, change)
INTERACTIONS = (
    ("c-pro", "cool-vc", "performance", 0.05),    # cooling sustains flagship clocks
    ("c-pro", "cam-1in", "camera", 0.04),         # flagship ISP suits a 1-inch sensor
    ("c-game", "cam-1in", "camera", 0.04),
    ("c-eff", "cam-1in", "camera", -0.12),        # efficiency ISP bottlenecks it
    ("c-eff", "aud-hifi", "audio", -0.05),        # limits hi-res decoding
)

PLACEMENT_RULES = {
    "camera": "Top of the frame, clear of the grip",
    "aux": "Beside the main camera",
    "audio": "Bottom edge, facing out",
    "net": "Top or bottom edge, the antenna window",
    "sensor": "Mid-frame, under the index finger",
    "compute": "Away from the battery",
    "cooling": "Touching the SoC",
    "battery": "Near the centre, for balance",
}
