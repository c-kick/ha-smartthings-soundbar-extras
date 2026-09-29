"""What setup offers per model, and the known OCF payload values."""

from dataclasses import dataclass

from .const import SETTINGS

# UI values are stable; Samsung's wire value for Adaptive is "adaptive sound".
SOUND_MODES = {
    "standard": "standard",
    "surround": "surround",
    "game": "game",
    "adaptive": "adaptive sound",
}
CHANNELS = {
    "center_level": "Spk_Center",
    "side_level": "Spk_Side",
    "wide_level": "Spk_Wide",
    "front_top_level": "Spk_Front_Top",
    "rear_level": "Spk_Rear",
    "rear_top_level": "Spk_Rear_Top",
    # Q990/Q995 manuals; opt-in only, not verified on a physical soundbar.
    "rear_side_level": "Spk_Rear_Side",
}
LEVELS = ("woofer_level", *CHANNELS)
EXTRA_CONTROLS = ("sound_mode", *LEVELS)
ALL_CONTROLS = (*SETTINGS, *EXTRA_CONTROLS)
MIN_LEVEL = -6
MAX_LEVEL = 6
# Not -12: below -6 the HW-Q930D snaps to a single -12 step (sent -8, the SmartThings
# app showed -12; 2026-09-29), so HA would show a value the soundbar doesn't have.
WOOFER_MIN = MIN_LEVEL
WOOFER_MAX = 6
TESTED_MODEL = "HW-Q930D"


@dataclass(frozen=True)
class Profile:
    """What setup offers and pre-selects. SmartThings can't tell us what a model supports."""

    offered: tuple[str, ...]
    defaults: tuple[str, ...]


def profile(model: str) -> Profile:
    base = model.upper().split("/", 1)[0]
    if base == TESTED_MODEL:
        tested = tuple(key for key in ALL_CONTROLS if key != "rear_side_level")
        return Profile(ALL_CONTROLS, tested)
    if base.startswith("HW-Q"):
        return Profile(ALL_CONTROLS, SETTINGS)
    return Profile(ALL_CONTROLS, ())


def valid_level(value, low: int = MIN_LEVEL, high: int = MAX_LEVEL) -> bool:
    """Reject fractional, non-finite and boolean values instead of truncating."""
    return (
        not isinstance(value, bool)
        and isinstance(value, (float, int))
        and low <= value <= high
        and int(value) == value
    )
