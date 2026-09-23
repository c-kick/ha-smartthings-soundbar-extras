"""The cloud sound-mode select shows confirmed local readback, with correct ordering."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data

from custom_components.soundbar_control.const import DOMAIN
from custom_components.soundbar_control.profiles import EXTRA_CONTROLS

from .conftest import DEVICE
from .local_fake import status
from .test_integration import setup


@pytest.fixture
def audio_local_entry(hass, local_entry):
    hass.config_entries.async_update_entry(
        local_entry,
        data={**local_entry.data, "settings": [*local_entry.data["settings"], *EXTRA_CONTROLS]},
    )
    return local_entry


def cloud_select(hass):
    return er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{DEVICE}_sound_mode")


async def ready(hass, entry):
    await setup(hass, entry)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_mapped_mode_is_confirmed(hass, parent, audio_local_entry, dependencies):
    await ready(hass, audio_local_entry)
    state = hass.states.get(cloud_select(hass))
    assert state.state == "adaptive"
    assert "assumed_state" not in state.attributes
    assert audio_local_entry.runtime_data.states["sound_mode"] == "adaptive"


async def test_extra_mode_shown_and_refused(
    hass, parent, audio_local_entry, local_client, dependencies
):
    local_client.value = status(sound_mode="MUSIC")
    await ready(hass, audio_local_entry)
    eid = cloud_select(hass)
    state = hass.states.get(eid)
    assert state.state == "MUSIC"
    assert "MUSIC" in state.attributes["options"]
    assert "sound_mode" not in audio_local_entry.runtime_data.states  # only cloud modes stored
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": eid, "option": "MUSIC"}, blocking=True
        )


async def test_failed_field_falls_back_to_assumed(
    hass, parent, audio_local_entry, local_client, dependencies
):
    local_client.value = status(sound_mode=None, failed=frozenset({"sound_mode"}))
    await ready(hass, audio_local_entry)
    state = hass.states.get(cloud_select(hass))
    assert state.state == "unknown"
    assert state.attributes["assumed_state"] is True


async def test_older_reading_does_not_confirm_after_cloud_command(
    hass, parent, audio_local_entry, local_client, dependencies
):
    await ready(hass, audio_local_entry)
    runtime = audio_local_entry.runtime_data
    eid = cloud_select(hass)
    # A poll starts, then a cloud command is accepted, then the poll finishes.
    local_client.value = status(sound_mode="STANDARD")
    local_client.gate = asyncio.Event()
    local_client.entered.clear()
    poll = hass.async_create_task(runtime.local.async_refresh())
    await local_client.entered.wait()
    # Isolate the ordering rule: the refresh a cloud command requests would start
    # after the command and legitimately confirm whatever the fake returns.
    with (
        patch.object(runtime.adapter, "command", new_callable=AsyncMock),
        patch.object(runtime.local, "async_request_refresh", new_callable=AsyncMock),
    ):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": eid, "option": "surround"}, blocking=True
        )
    local_client.gate.set()
    await poll
    await hass.async_block_till_done()
    state = hass.states.get(eid)
    assert state.state == "surround"  # the commanded value, not the older "standard"
    assert state.attributes["assumed_state"] is True
    # The next poll starts after the command, so it confirms.
    local_client.gate = None
    local_client.value = status(sound_mode="SURROUND")
    await runtime.local.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(eid)
    assert state.state == "surround"
    assert "assumed_state" not in state.attributes


async def test_cloud_command_requests_local_refresh(hass, parent, audio_local_entry, dependencies):
    await ready(hass, audio_local_entry)
    runtime = audio_local_entry.runtime_data
    with (
        patch.object(runtime.adapter, "command", new_callable=AsyncMock),
        patch.object(runtime.local, "async_request_refresh", new_callable=AsyncMock) as refresh,
    ):
        await hass.services.async_call(
            "select", "select_option",
            {"entity_id": cloud_select(hass), "option": "game"}, blocking=True,
        )  # fmt: skip
        await hass.async_block_till_done(wait_background_tasks=True)
    refresh.assert_awaited()


async def test_extra_options_restored(hass, parent, audio_local_entry, dependencies):
    registry = er.async_get(hass)
    eid = registry.async_get_or_create(
        "select", DOMAIN, f"{DEVICE}_sound_mode", config_entry=audio_local_entry
    ).entity_id
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(eid, "unavailable"),
                {"assumed_value": "adaptive", "extra_options": ["MUSIC", "a;b"]},
            )
        ],
    )
    await setup(hass, audio_local_entry)
    options = hass.states.get(eid).attributes["options"]
    assert "MUSIC" in options
    assert "a;b" not in options


async def test_legacy_restore_without_local_data(
    hass, parent, audio_local_entry, local_client, dependencies
):
    """2.1 stored only the assumed value; restore it while local data is pending."""
    local_client.gate = asyncio.Event()  # the first local reading never finishes here
    registry = er.async_get(hass)
    eid = registry.async_get_or_create(
        "select", DOMAIN, f"{DEVICE}_sound_mode", config_entry=audio_local_entry
    ).entity_id
    mock_restore_cache_with_extra_data(
        hass, [(State(eid, "surround"), {"assumed_value": "surround"})]
    )
    await setup(hass, audio_local_entry)
    assert audio_local_entry.runtime_data.local.data is None
    state = hass.states.get(eid)
    assert state.state == "surround"
    assert state.attributes["assumed_state"] is True
    assert state.attributes["options"] == ["standard", "surround", "game", "adaptive"]
    local_client.gate.set()
    await hass.async_block_till_done(wait_background_tasks=True)
