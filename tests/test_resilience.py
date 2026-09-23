"""Availability after stale parent snapshots, and assumed values surviving shutdown."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import restore_state
from homeassistant.helpers.restore_state import STORAGE_KEY
from pysmartthings import SmartThingsConnectionError
from pytest_homeassistant_custom_component.common import (
    mock_restore_cache,
    mock_restore_cache_with_extra_data,
)

from custom_components.soundbar_control.const import DOMAIN
from custom_components.soundbar_control.profiles import EXTRA_CONTROLS

from .conftest import DEVICE, fire, health
from .test_integration import setup


@pytest.fixture
def stale_offline(parent):
    """SmartThings loaded while the soundbar was offline and never updates the flag."""
    parent.runtime_data.devices[DEVICE].online = False
    return parent


async def test_stale_offline_snapshot_is_corrected_by_health_read(
    hass, stale_offline, entry, dependencies
):
    await setup(hass, entry)
    await hass.async_block_till_done(wait_background_tasks=True)
    stale_offline.runtime_data.client.get_device_health.assert_awaited_once_with(DEVICE)
    assert entry.runtime_data.available
    entity_id = er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"{DEVICE}_nightmode")
    assert hass.states.get(entity_id).state != "unavailable"


async def test_health_read_failure_keeps_snapshot(hass, stale_offline, entry, dependencies):
    stale_offline.runtime_data.client.get_device_health.side_effect = SmartThingsConnectionError(
        "down"
    )
    await setup(hass, entry)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not entry.runtime_data.available


async def test_newer_health_event_wins_over_slow_read(hass, parent, entry, dependencies):
    gate = asyncio.Event()

    async def slow_read(device_id):
        await gate.wait()
        return health("ONLINE")

    parent.runtime_data.client.get_device_health = AsyncMock(side_effect=slow_read)
    await setup(hass, entry)
    fire(parent.runtime_data.client, "DEVICE_HEALTH_EVENT", status="OFFLINE")
    gate.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not entry.runtime_data.available


async def test_health_read_is_cancelled_on_unload(hass, parent, entry, dependencies):
    started = asyncio.Event()

    async def never_answers(device_id):
        started.set()
        await asyncio.Event().wait()

    parent.runtime_data.client.get_device_health = AsyncMock(side_effect=never_answers)
    await setup(hass, entry)
    await started.wait()
    assert await hass.config_entries.async_unload(entry.entry_id)
    # Would hang until the test timeout if unload left the read running.
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.fixture
def audio_entry(hass, entry):
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "settings": [*entry.data["settings"], *EXTRA_CONTROLS]}
    )
    return entry


def registered(hass, entry, domain, key):
    return (
        er.async_get(hass)
        .async_get_or_create(domain, DOMAIN, f"{DEVICE}_{key}", config_entry=entry)
        .entity_id
    )


async def test_values_survive_unavailable_state_at_shutdown(
    hass, parent, audio_entry, dependencies
):
    night = registered(hass, audio_entry, "switch", "nightmode")
    bass = registered(hass, audio_entry, "switch", "bassboost")
    mode = registered(hass, audio_entry, "select", "sound_mode")
    mock_restore_cache_with_extra_data(
        hass,
        [
            (State(night, "unavailable"), {"assumed_value": True}),
            (State(bass, "unavailable"), {"assumed_value": False}),
            (State(mode, "unavailable"), {"assumed_value": "adaptive"}),
        ],
    )
    await setup(hass, audio_entry)
    assert hass.states.get(night).state == "on"
    assert hass.states.get(bass).state == "off"
    assert hass.states.get(mode).state == "adaptive"


async def test_value_is_saved_while_unavailable(
    hass, hass_storage, parent, audio_entry, dependencies
):
    await setup(hass, audio_entry)
    registry = er.async_get(hass)
    night = registry.async_get_entity_id("switch", DOMAIN, f"{DEVICE}_nightmode")
    with patch.object(audio_entry.runtime_data.adapter, "command", new_callable=AsyncMock):
        await hass.services.async_call("switch", "turn_on", {"entity_id": night}, blocking=True)
    fire(parent.runtime_data.client, "DEVICE_HEALTH_EVENT", status="OFFLINE")
    assert hass.states.get(night).state == "unavailable"
    await restore_state.async_get(hass).async_dump_states()
    saved = {item["state"]["entity_id"]: item for item in hass_storage[STORAGE_KEY]["data"]}
    assert saved[night]["state"]["state"] == "unavailable"
    assert saved[night]["extra_data"] == {"assumed_value": True}


async def test_state_saved_before_upgrade_is_still_restored(
    hass, parent, audio_entry, dependencies
):
    night = registered(hass, audio_entry, "switch", "nightmode")
    mode = registered(hass, audio_entry, "select", "sound_mode")
    mock_restore_cache(hass, [State(night, "on"), State(mode, "surround")])
    await setup(hass, audio_entry)
    assert hass.states.get(night).state == "on"
    assert hass.states.get(mode).state == "surround"


async def test_invalid_saved_values_stay_unknown(hass, parent, audio_entry, dependencies):
    night = registered(hass, audio_entry, "switch", "nightmode")
    mode = registered(hass, audio_entry, "select", "sound_mode")
    mock_restore_cache_with_extra_data(
        hass,
        [
            (State(night, "unavailable"), {"assumed_value": "yes"}),
            (State(mode, "unavailable"), {"assumed_value": "loud"}),
        ],
    )
    await setup(hass, audio_entry)
    assert hass.states.get(night).state == "unknown"
    assert hass.states.get(mode).state == "unknown"
