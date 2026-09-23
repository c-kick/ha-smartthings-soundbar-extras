"""Model-scoped controls backed by Samsung's manual and known OCF payloads."""

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
}
LEVELS = ("woofer_level", *CHANNELS)
EXTRA_CONTROLS = ("sound_mode", *LEVELS)
MIN_LEVEL = -6
MAX_LEVEL = 6


def has_q930d_profile(model: str) -> bool:
    return model.upper().split("/", 1)[0] == "HW-Q930D"


def available_controls(model: str) -> tuple[str, ...]:
    return (*SETTINGS, *EXTRA_CONTROLS) if has_q930d_profile(model) else SETTINGS


def valid_level(value) -> bool:
    """Reject fractional, non-finite and boolean values instead of truncating."""
    return (
        not isinstance(value, bool)
        and isinstance(value, (float, int))
        and MIN_LEVEL <= value <= MAX_LEVEL
        and int(value) == value
    )
