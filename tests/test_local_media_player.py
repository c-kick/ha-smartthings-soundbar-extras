"""Player (local): one media player over the local API, optional and on by default."""

import pytest
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data

from custom_components.soundbar_control.const import DOMAIN
from custom_components.soundbar_control.local_api import (
    KNOWN_INPUTS,
    KNOWN_SOUND_MODES,
    LocalApiError,
    LocalApiUnreachable,
)

from .conftest import DEVICE
from .local_fake import status
from .test_local_entities import ready

UNIQUE_ID = f"{DEVICE}_player_local"


def player(hass):
    return er.async_get(hass).async_get_entity_id("media_player", DOMAIN, UNIQUE_ID)


async def call(hass, service, **data):
    await hass.services.async_call(
        "media_player", service, {"entity_id": player(hass), **data}, blocking=True
    )


async def test_state_and_attributes(hass, parent, local_entry, dependencies):
    await ready(hass, local_entry)
    eid = player(hass)
    assert eid.endswith("player_local")
    state = hass.states.get(eid)
    assert state.name.endswith("Player (local)")
    assert state.state == "on"
    assert state.attributes["device_class"] == "speaker"
    assert state.attributes["volume_level"] == 0.1
    assert state.attributes["is_volume_muted"] is False
    assert state.attributes["source"] == "E_ARC"
    assert state.attributes["source_list"] == list(KNOWN_INPUTS)
    assert state.attributes["sound_mode"] == "ADAPTIVE"
    assert state.attributes["sound_mode_list"] == list(KNOWN_SOUND_MODES)
    assert "assumed_state" not in state.attributes
    features = MediaPlayerEntityFeature(state.attributes["supported_features"])
    for feature in (
        MediaPlayerEntityFeature.TURN_ON,
        MediaPlayerEntityFeature.TURN_OFF,
        MediaPlayerEntityFeature.VOLUME_SET,
        MediaPlayerEntityFeature.VOLUME_STEP,
        MediaPlayerEntityFeature.VOLUME_MUTE,
        MediaPlayerEntityFeature.SELECT_SOURCE,
        MediaPlayerEntityFeature.SELECT_SOUND_MODE,
    ):
        assert feature in features, feature
    assert MediaPlayerEntityFeature.PLAY not in features


async def test_off(hass, parent, local_entry, local_client, dependencies):
    local_client.value = status(power=False)
    await ready(hass, local_entry)
    assert hass.states.get(player(hass)).state == "off"


@pytest.mark.parametrize(
    ("service", "data", "write"),
    [
        ("turn_off", {}, ("power", False)),
        ("turn_on", {}, ("power", True)),
        ("volume_set", {"volume_level": 0.25}, ("volume", 25)),
        ("volume_up", {}, ("volume", 11)),
        ("volume_down", {}, ("volume", 9)),
        ("volume_mute", {"is_volume_muted": True}, ("muted", True)),
        ("select_source", {"source": "BT"}, ("input", "BT")),
        ("select_sound_mode", {"sound_mode": "MUSIC"}, ("sound_mode", "MUSIC")),
    ],
)
async def test_commands(
    hass, parent, local_entry, local_client, dependencies, service, data, write
):
    await ready(hass, local_entry)
    await call(hass, service, **data)
    assert local_client.writes == [write]


async def test_quick_volume_steps_add_up(hass, parent, local_entry, local_client, dependencies):
    await ready(hass, local_entry)
    for _ in range(3):
        await call(hass, "volume_up")
    assert local_client.writes == [("volume", 11), ("volume", 12), ("volume", 13)]
    assert hass.states.get(player(hass)).attributes["volume_level"] == 0.13


async def test_volume_stays_in_range(hass, parent, local_entry, local_client, dependencies):
    local_client.value = status(volume=100)
    await ready(hass, local_entry)
    await call(hass, "volume_up")
    assert local_client.writes == [("volume", 100)]


async def test_rejected_command_raises(hass, parent, local_entry, local_client, dependencies):
    await ready(hass, local_entry)
    local_client.write_error = LocalApiError("rejected")
    with pytest.raises(HomeAssistantError):
        await call(hass, "select_source", source="BT")
    assert hass.states.get(player(hass)).attributes["source"] == "E_ARC"


async def test_failed_field_leaves_player_available(
    hass, parent, local_entry, local_client, dependencies
):
    local_client.value = status(volume=None, failed=frozenset({"volume"}))
    await ready(hass, local_entry)
    state = hass.states.get(player(hass))
    assert state.state == "on"
    assert "volume_level" not in state.attributes


async def test_unavailable_without_power(hass, parent, local_entry, local_client, dependencies):
    local_client.value = status(power=None, failed=frozenset({"power"}))
    await ready(hass, local_entry)
    assert hass.states.get(player(hass)).state == "unavailable"


async def test_unavailable_when_polls_fail(hass, parent, local_entry, local_client, dependencies):
    await ready(hass, local_entry)
    local_client.error = LocalApiUnreachable("down")
    await local_entry.runtime_data.local.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(player(hass)).state == "unavailable"


async def test_reported_values_join_the_lists(
    hass, parent, local_entry, local_client, dependencies
):
    local_client.value = status(input="WIFI_SPOIFY", sound_mode="DOLBY")
    await ready(hass, local_entry)
    state = hass.states.get(player(hass))
    assert state.attributes["source"] == "WIFI_SPOIFY"
    assert "WIFI_SPOIFY" in state.attributes["source_list"]
    assert "DOLBY" in state.attributes["sound_mode_list"]


async def test_reported_values_restored(hass, parent, local_entry, dependencies):
    eid = (
        er.async_get(hass)
        .async_get_or_create("media_player", DOMAIN, UNIQUE_ID, config_entry=local_entry)
        .entity_id
    )
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(eid, "unavailable"),
                {"inputs": ["WIFI_SPOIFY", "bad;value"], "sound_modes": ["DOLBY"]},
            )
        ],
    )
    await ready(hass, local_entry)
    attributes = hass.states.get(eid).attributes
    assert "WIFI_SPOIFY" in attributes["source_list"]
    assert "bad;value" not in attributes["source_list"]
    assert "DOLBY" in attributes["sound_mode_list"]


async def test_no_player_without_local_api(hass, parent, entry, dependencies):
    await ready(hass, entry)
    assert player(hass) is None


async def test_option_off_removes_player(hass, parent, local_entry, dependencies):
    await ready(hass, local_entry)
    assert player(hass) is not None
    hass.config_entries.async_update_entry(
        local_entry, options={**local_entry.options, "media_player": False}
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert player(hass) is None
