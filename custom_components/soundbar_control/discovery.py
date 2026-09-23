"""Soundbars seen in AirPlay broadcasts, for the local API address field."""

from __future__ import annotations

from dataclasses import dataclass

from .const import DOMAIN


@dataclass(frozen=True)
class Advertised:
    host: str
    name: str


def discovered_soundbars(hass) -> dict[str, Advertised]:
    """Lowercase MAC -> last advertised address. Lives only in memory."""
    return hass.data.setdefault(DOMAIN, {}).setdefault("discovered", {})
