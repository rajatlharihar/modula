"""The offline explanation: two sentences written only from computed facts."""
from .catalogue import DIMS, DIM_LABELS


def template_explanation(build, need):
    ranked = sorted(DIMS, key=lambda d: -need.get(d, 0))
    weakest = min(DIMS, key=lambda d: build.config.vec[d])
    if need[ranked[0]] == need[ranked[-1]]:
        opening = "No priority stands out, so this is a general build"
    else:
        opening = f"This build puts {DIM_LABELS[ranked[0]].lower()} and {DIM_LABELS[ranked[1]].lower()} first"
    return (f"{opening}, "
            f"at ₹{build.config.price:,} and {round(build.config.mass)} g, with about "
            f"{build.config.hours:.1f} hours of mixed use. It gives up the most on "
            f"{DIM_LABELS[weakest].lower()}.")
