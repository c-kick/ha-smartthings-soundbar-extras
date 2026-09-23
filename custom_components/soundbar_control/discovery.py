"""Soundbars seen in AirPlay broadcasts, and moving a pinned connection to a new address.

An advertisement alone never changes anything: a new address is used only after it
presents the pinned certificate, and only the local connection moves (no reload).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .const import CONF_CERT, CONF_HOST, CONF_USE_LOCAL, DOMAIN
from .local_api import LocalApiException, fetch_certificate_sha256

_LOGGER = logging.getLogger(__name__)
RECHECK_AFTER = 600.0


@dataclass(frozen=True)
class Advertised:
    host: str
    name: str


@dataclass
class _CheckState:
    running: bool = False
    recent: dict[str, float] = field(default_factory=dict)


def _data(hass) -> dict:
    return hass.data.setdefault(DOMAIN, {})


def discovered_soundbars(hass) -> dict[str, Advertised]:
    """Lowercase MAC -> last advertised address. Lives only in memory."""
    return _data(hass).setdefault("discovered", {})


def remember(hass, mac: str, host: str, name: str) -> None:
    discovered_soundbars(hass)[mac.lower()] = Advertised(host, name)


async def async_check_address(hass, entry, host: str, *, clock=time.monotonic) -> bool:
    """Move the entry's local connection to host if it presents the pinned certificate."""
    options = entry.options
    if not options.get(CONF_USE_LOCAL) or host == options.get(CONF_HOST):
        return False
    state = _data(hass).setdefault("checks", {}).setdefault(entry.entry_id, _CheckState())
    now = clock()
    if state.running or now - state.recent.get(host, float("-inf")) < RECHECK_AFTER:
        return False
    state.running = True
    state.recent[host] = now
    try:
        try:
            sha = await fetch_certificate_sha256(host)
        except LocalApiException:
            _LOGGER.debug("Advertised soundbar address did not answer; ignored")
            return False
        if sha != options[CONF_CERT]:
            _LOGGER.debug("Advertised soundbar address presented another certificate; ignored")
            return False
        # The options listener applies a host-only change in place, without reloading.
        hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_HOST: host})
        return True
    finally:
        state.running = False
