"""Model gating, safe writes, restore state, and exact Samsung audio payloads."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
    mock_restore_cache_with_extra_data,
)

from custom_components.soundbar_control.const import DOMAIN, PREFIX
from custom_components.soundbar_control.profiles import CHANNELS, EXTRA_CONTROLS, SOUND_MODES

from .conftest import DEVICE
from .test_integration import setup


@pytest.fixture
def audio_entry(hass, entry):
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "settings": [*entry.data["settings"], *EXTRA_CONTROLS]}
    )
    return entry


async def test_new_entities_start_unknown_without_commands(hass, parent, audio_entry, dependencies):
    with patch(
        "custom_components.soundbar_control.smartthings.SmartThingsAdapter.command",
        new_callable=AsyncMock,
    ) as command:
        await setup(hass, audio_entry)
        assert (
            len(er.async_entries_for_config_entry(er.async_get(hass), audio_entry.entry_id)) == 13
        )
        for key in EXTRA_CONTROLS:
            domain = "select" if key == "sound_mode" else "number"
            entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{DEVICE}_{key}")
            state = hass.states.get(entity_id)
            assert state.state == "unknown"
            assert state.attributes["assumed_state"] is True
        command.assert_not_called()


@pytest.mark.parametrize("option,wire", SOUND_MODES.items())
async def test_sound_mode_payload(hass, parent, audio_entry, dependencies, option, wire):
    await setup(hass, audio_entry)
    entity_id = er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{DEVICE}_sound_mode")
    with patch.object(
        audio_entry.runtime_data.adapter, "command", new_callable=AsyncMock
    ) as command:
        await hass.services.async_call(
            "select", "select_option", {"entity_id": entity_id, "option": option}, blocking=True
        )
        command.assert_awaited_once_with(
            "execute", "execute", ["/sec/networkaudio/soundmode", {f"{PREFIX}soundmode": wire}]
        )
        assert hass.states.get(entity_id).state == option
        command.side_effect = HomeAssistantError("rejected")
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "select",
                "select_option",
                {"entity_id": entity_id, "option": "standard"},
                blocking=True,
            )
        assert hass.states.get(entity_id).state == option


@pytest.mark.parametrize("key,channel", CHANNELS.items())
async def test_channel_payload_changes_only_selected_channel(
    hass, parent, audio_entry, dependencies, key, channel
):
    await setup(hass, audio_entry)
    entity_id = er.async_get(hass).async_get_entity_id("number", DOMAIN, f"{DEVICE}_{key}")
    with patch.object(
        audio_entry.runtime_data.adapter, "command", new_callable=AsyncMock
    ) as command:
        await hass.services.async_call(
            "number", "set_value", {"entity_id": entity_id, "value": -3}, blocking=True
        )
        command.assert_awaited_once_with(
            "execute",
            "execute",
            [
                "/sec/networkaudio/channelVolume",
                {f"{PREFIX}channelVolume": [{"name": channel, "value": -3}]},
            ],
        )
        assert hass.states.get(entity_id).state == "-3"


async def test_woofer_payload_and_failure(hass, parent, audio_entry, dependencies):
    await setup(hass, audio_entry)
    runtime = audio_entry.runtime_data
    with patch.object(runtime.adapter, "command", new_callable=AsyncMock) as command:
        await runtime.set_level("woofer_level", 2)
        command.assert_awaited_once_with(
            "execute", "execute", ["/sec/networkaudio/woofer", {f"{PREFIX}woofer": 2}]
        )
        command.side_effect = HomeAssistantError("401")
        with pytest.raises(HomeAssistantError):
            await runtime.set_level("woofer_level", 0)
        assert runtime.states["woofer_level"] == 2


@pytest.mark.parametrize("value", [-7, 7, 1.5, True, float("nan"), float("inf"), "3"])
async def test_invalid_level_never_sends_command(hass, parent, audio_entry, dependencies, value):
    await setup(hass, audio_entry)
    with patch.object(
        audio_entry.runtime_data.adapter, "command", new_callable=AsyncMock
    ) as command:
        with pytest.raises(HomeAssistantError):
            await audio_entry.runtime_data.set_level("center_level", value)
        command.assert_not_called()


async def test_disabled_control_and_invalid_mode(hass, parent, entry, dependencies):
    await setup(hass, entry)
    with patch.object(entry.runtime_data.adapter, "command", new_callable=AsyncMock) as command:
        with pytest.raises(HomeAssistantError):
            await entry.runtime_data.set_sound_mode("surround")
        with pytest.raises(HomeAssistantError):
            await entry.runtime_data.set_sound_mode("invalid")
        command.assert_not_called()


async def test_minor_upgrade_enables_controls_once(hass, parent, dependencies):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=1,
        unique_id=DEVICE,
        data={
            "parent_entry_id": parent.entry_id,
            "device_id": DEVICE,
            "model": "HW-Q930D",
            "name": "Test",
            "settings": ["nightmode"],
        },
    )
    entry.add_to_hass(hass)
    await setup(hass, entry)
    assert entry.minor_version == 2
    assert entry.data["settings"] == ["nightmode", *EXTRA_CONTROLS]
    # A later reconfigure choice is not undone by another restart/reload.
    hass.config_entries.async_update_entry(entry, data={**entry.data, "settings": ["nightmode"]})
    assert await hass.config_entries.async_reload(entry.entry_id)
    assert entry.data["settings"] == ["nightmode"]


async def test_unprofiled_model_does_not_get_extra_entities(
    hass, parent, audio_entry, dependencies
):
    hass.config_entries.async_update_entry(
        audio_entry, data={**audio_entry.data, "model": "HW-UNKNOWN"}
    )
    await setup(hass, audio_entry)
    assert len(er.async_entries_for_config_entry(er.async_get(hass), audio_entry.entry_id)) == 5
    with patch.object(
        audio_entry.runtime_data.adapter, "command", new_callable=AsyncMock
    ) as command:
        with pytest.raises(HomeAssistantError):
            await audio_entry.runtime_data.set_level("woofer_level", 0)
        command.assert_not_called()


async def test_sound_mode_restored_without_command(hass, parent, audio_entry, dependencies):
    registry = er.async_get(hass)
    previous = registry.async_get_or_create(
        "select", DOMAIN, f"{DEVICE}_sound_mode", config_entry=audio_entry
    )
    mock_restore_cache(hass, [State(previous.entity_id, "adaptive")])
    with patch(
        "custom_components.soundbar_control.smartthings.SmartThingsAdapter.command",
        new_callable=AsyncMock,
    ) as command:
        await setup(hass, audio_entry)
        assert hass.states.get(previous.entity_id).state == "adaptive"
        command.assert_not_called()


@pytest.mark.parametrize("level,expected", [(3, "3"), (0, "0"), (-6, "-6"), (7, "unknown")])
async def test_level_restored_without_command(
    hass, parent, audio_entry, dependencies, level, expected
):
    registry = er.async_get(hass)
    previous = registry.async_get_or_create(
        "number", DOMAIN, f"{DEVICE}_center_level", config_entry=audio_entry
    )
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(previous.entity_id, str(level)),
                {
                    "native_min_value": -6,
                    "native_max_value": 6,
                    "native_step": 1,
                    "native_unit_of_measurement": "dB",
                    "native_value": level,
                },
            )
        ],
    )
    with patch(
        "custom_components.soundbar_control.smartthings.SmartThingsAdapter.command",
        new_callable=AsyncMock,
    ) as command:
        await setup(hass, audio_entry)
        assert hass.states.get(previous.entity_id).state == expected
        command.assert_not_called()
