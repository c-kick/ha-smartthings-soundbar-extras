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

from custom_components.soundbar_control.const import DOMAIN, PREFIX, SETTINGS
from custom_components.soundbar_control.profiles import (
    ALL_CONTROLS,
    CHANNELS,
    EXTRA_CONTROLS,
    SOUND_MODES,
    profile,
)

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
    assert entry.data["settings"] == [
        "nightmode",
        *[k for k in EXTRA_CONTROLS if k != "rear_side_level"],
    ]
    # A later reconfigure choice is not undone by another restart/reload.
    hass.config_entries.async_update_entry(entry, data={**entry.data, "settings": ["nightmode"]})
    assert await hass.config_entries.async_reload(entry.entry_id)
    assert entry.data["settings"] == ["nightmode"]


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


@pytest.mark.parametrize(
    "model", ["HW-Q930D", "HW-Q930D/ZF", "hw-q930d", "HW-Q990F", "HW-S800D", ""]
)
def test_every_model_is_offered_every_control(model):
    assert profile(model).offered == ALL_CONTROLS


@pytest.mark.parametrize(
    ("model", "defaults"),
    [
        ("HW-Q930D", tuple(k for k in ALL_CONTROLS if k != "rear_side_level")),
        ("HW-Q930D/ZF", tuple(k for k in ALL_CONTROLS if k != "rear_side_level")),
        ("hw-q930d", tuple(k for k in ALL_CONTROLS if k != "rear_side_level")),
        ("HW-Q990F", SETTINGS),
        ("HW-QS730D", SETTINGS),
        ("HW-S800D", ()),
        ("", ()),
    ],
)
def test_defaults(model, defaults):
    assert profile(model).defaults == defaults


async def test_rear_side_payload(hass, parent, audio_entry, dependencies):
    await setup(hass, audio_entry)
    runtime = audio_entry.runtime_data
    with patch.object(runtime.adapter, "command", new_callable=AsyncMock) as command:
        await runtime.set_level("rear_side_level", -2)
        command.assert_awaited_once_with(
            "execute",
            "execute",
            ["/sec/networkaudio/channelVolume",
             {f"{PREFIX}channelVolume": [{"name": "Spk_Rear_Side", "value": -2}]}],
        )  # fmt: skip


async def test_untested_model_gets_what_it_enabled(hass, parent, audio_entry, dependencies):
    hass.config_entries.async_update_entry(
        audio_entry, data={**audio_entry.data, "model": "HW-S800D"}
    )
    await setup(hass, audio_entry)
    assert len(er.async_entries_for_config_entry(er.async_get(hass), audio_entry.entry_id)) == 13


async def test_existing_entry_keeps_its_controls(hass, parent, entry, dependencies):
    old_defaults = [k for k in ALL_CONTROLS if k != "rear_side_level"]
    hass.config_entries.async_update_entry(entry, data={**entry.data, "settings": old_defaults})
    await setup(hass, entry)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("number", DOMAIN, f"{DEVICE}_rear_side_level") is None
    assert entry.data["settings"] == old_defaults


async def test_woofer_stops_at_minus_six(hass, parent, audio_entry, dependencies):
    """Below -6 the HW-Q930D snaps to a single -12 step, so HA would show a wrong value."""
    await setup(hass, audio_entry)
    eid = er.async_get(hass).async_get_entity_id("number", DOMAIN, f"{DEVICE}_woofer_level")
    assert hass.states.get(eid).attributes["min"] == -6


@pytest.mark.parametrize("value", [-12, -8, -7, 7])
async def test_woofer_outside_range_never_sent(hass, parent, audio_entry, dependencies, value):
    await setup(hass, audio_entry)
    runtime = audio_entry.runtime_data
    with patch.object(runtime.adapter, "command", new_callable=AsyncMock) as command:
        with pytest.raises(HomeAssistantError):
            await runtime.set_level("woofer_level", value)
        command.assert_not_called()


@pytest.mark.parametrize(("stored", "kept"), [(-6, "-6"), (-10, "unknown")])
async def test_woofer_restore_uses_the_range(hass, parent, audio_entry, dependencies, stored, kept):
    eid = (
        er.async_get(hass)
        .async_get_or_create("number", DOMAIN, f"{DEVICE}_woofer_level", config_entry=audio_entry)
        .entity_id
    )
    mock_restore_cache_with_extra_data(
        hass,
        [(State(eid, str(stored)), {"native_value": stored, "native_unit_of_measurement": "dB",
          "native_min_value": -12, "native_max_value": 6, "native_step": 1})],
    )  # fmt: skip
    await setup(hass, audio_entry)
    assert hass.states.get(eid).state == kept


async def test_channel_levels_stay_within_six(hass, parent, audio_entry, dependencies):
    await setup(hass, audio_entry)
    eid = er.async_get(hass).async_get_entity_id("number", DOMAIN, f"{DEVICE}_center_level")
    assert hass.states.get(eid).attributes["min"] == -6
