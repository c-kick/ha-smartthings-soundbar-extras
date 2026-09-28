"""The six _local entities: naming, availability, readback, writes and restore."""

import pytest
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data

from custom_components.soundbar_control.const import DOMAIN
from custom_components.soundbar_control.local_api import LocalApiError, LocalApiUnreachable

from .conftest import DEVICE
from .local_fake import status
from .test_integration import setup

LOCAL = {
    "sensor": ["audio_codec_local"],
    "select": ["input_local", "sound_mode_local"],
    "switch": ["power_local", "mute_local"],
    "number": ["volume_local"],
}


def entity_id(hass, platform, key):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{DEVICE}_{key}")


async def ready(hass, entry):
    await setup(hass, entry)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_ids_and_names(hass, parent, local_entry, dependencies):
    await ready(hass, local_entry)
    for platform, keys in LOCAL.items():
        for key in keys:
            eid = entity_id(hass, platform, key)
            assert eid is not None, key
            assert eid.endswith(key), eid
            assert hass.states.get(eid).name.endswith("(local)")


async def test_no_local_entities_without_local_api(hass, parent, entry, dependencies):
    await ready(hass, entry)
    assert entity_id(hass, "sensor", "audio_codec_local") is None


async def test_readback(hass, parent, local_entry, dependencies):
    await ready(hass, local_entry)
    assert hass.states.get(entity_id(hass, "sensor", "audio_codec_local")).state == "DTS"
    assert hass.states.get(entity_id(hass, "select", "input_local")).state == "E_ARC"
    assert hass.states.get(entity_id(hass, "select", "sound_mode_local")).state == "ADAPTIVE"
    assert hass.states.get(entity_id(hass, "switch", "power_local")).state == "on"
    assert hass.states.get(entity_id(hass, "switch", "mute_local")).state == "off"
    assert hass.states.get(entity_id(hass, "number", "volume_local")).state == "10"
    for platform, keys in LOCAL.items():
        for key in keys:
            assert "assumed_state" not in hass.states.get(entity_id(hass, platform, key)).attributes


async def test_unavailable_before_first_data(hass, parent, local_entry, local_client, dependencies):
    import asyncio

    local_client.gate = asyncio.Event()
    await setup(hass, local_entry)
    assert hass.states.get(entity_id(hass, "sensor", "audio_codec_local")).state == "unavailable"
    local_client.gate.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(entity_id(hass, "sensor", "audio_codec_local")).state == "DTS"


async def test_failed_field_only_affects_its_entity(
    hass, parent, local_entry, local_client, dependencies
):
    local_client.value = status(codec=None, failed=frozenset({"codec"}))
    await ready(hass, local_entry)
    assert hass.states.get(entity_id(hass, "sensor", "audio_codec_local")).state == "unavailable"
    assert hass.states.get(entity_id(hass, "number", "volume_local")).state == "10"


async def test_empty_codec_is_unknown_but_available(
    hass, parent, local_entry, local_client, dependencies
):
    local_client.value = status(codec=None)
    await ready(hass, local_entry)
    assert hass.states.get(entity_id(hass, "sensor", "audio_codec_local")).state == "unknown"


async def test_poll_failure_makes_all_local_unavailable(
    hass, parent, local_entry, local_client, dependencies
):
    await ready(hass, local_entry)
    local_client.error = LocalApiUnreachable("down")
    await local_entry.runtime_data.local.async_refresh()
    await hass.async_block_till_done()
    for platform, keys in LOCAL.items():
        for key in keys:
            assert hass.states.get(entity_id(hass, platform, key)).state == "unavailable"


@pytest.mark.parametrize(
    ("domain", "service", "platform", "key", "data", "write"),
    [
        (
            "select",
            "select_option",
            "select",
            "input_local",
            {"option": "HDMI_IN1"},
            ("input", "HDMI_IN1"),
        ),
        (
            "select",
            "select_option",
            "select",
            "sound_mode_local",
            {"option": "GAME"},
            ("sound_mode", "GAME"),
        ),
        ("switch", "turn_off", "switch", "power_local", {}, ("power", False)),
        ("switch", "turn_on", "switch", "mute_local", {}, ("muted", True)),
        ("number", "set_value", "number", "volume_local", {"value": 25}, ("volume", 25)),
    ],
)
async def test_writes(
    hass,
    parent,
    local_entry,
    local_client,
    dependencies,
    domain,
    service,
    platform,
    key,
    data,
    write,
):
    await ready(hass, local_entry)
    await hass.services.async_call(
        domain, service, {"entity_id": entity_id(hass, platform, key), **data}, blocking=True
    )
    assert local_client.writes == [write]


async def test_rejected_write_raises_and_keeps_readback(
    hass, parent, local_entry, local_client, dependencies
):
    await ready(hass, local_entry)
    local_client.write_error = LocalApiError("rejected")
    eid = entity_id(hass, "select", "sound_mode_local")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": eid, "option": "MUSIC"}, blocking=True
        )
    assert hass.states.get(eid).state == "ADAPTIVE"


async def test_fractional_volume_rejected(hass, parent, local_entry, local_client, dependencies):
    await ready(hass, local_entry)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number", "set_value",
            {"entity_id": entity_id(hass, "number", "volume_local"), "value": 25.5},
            blocking=True,
        )  # fmt: skip
    assert local_client.writes == []


async def test_observed_value_becomes_option_and_survives_restart(
    hass, parent, local_entry, local_client, dependencies
):
    local_client.value = status(input="WIFI_AIRPLAY")
    await ready(hass, local_entry)
    eid = entity_id(hass, "select", "input_local")
    assert hass.states.get(eid).state == "WIFI_AIRPLAY"
    assert "WIFI_AIRPLAY" in hass.states.get(eid).attributes["options"]


async def test_observed_options_restored(hass, parent, local_entry, dependencies):
    registry = er.async_get(hass)
    eid = registry.async_get_or_create(
        "select", DOMAIN, f"{DEVICE}_input_local", config_entry=local_entry
    ).entity_id
    mock_restore_cache_with_extra_data(
        hass,
        [(State(eid, "unavailable"), {"observed": ["WIFI_AIRPLAY", "bad;value", "x" * 80]})],
    )
    await ready(hass, local_entry)
    options = hass.states.get(eid).attributes["options"]
    assert "WIFI_AIRPLAY" in options
    assert "bad;value" not in options


async def test_accepted_write_shows_before_next_read(
    hass, parent, local_entry, local_client, dependencies
):
    """A second quick write shows at once, although HA debounces its refresh."""
    await ready(hass, local_entry)
    eid = entity_id(hass, "number", "volume_local")
    for value in (25, 30):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": eid, "value": value}, blocking=True
        )
    assert hass.states.get(eid).state == "30"


async def test_accepted_write_keeps_read_time(hass, parent, local_entry, dependencies):
    """Showing a written value must not pass for a fresh reading of the soundbar."""
    await ready(hass, local_entry)
    local = local_entry.runtime_data.local
    eid = entity_id(hass, "switch", "mute_local")
    await hass.services.async_call("switch", "turn_on", {"entity_id": eid}, blocking=True)
    last_read = local.data.read_started
    # This write's refresh is debounced, so only the written value changes.
    await hass.services.async_call("switch", "turn_off", {"entity_id": eid}, blocking=True)
    assert local.data.muted is False
    assert local.data.read_started == last_read


async def test_write_while_polls_fail_stays_unavailable(
    hass, parent, local_entry, local_client, dependencies
):
    await ready(hass, local_entry)
    local_client.error = LocalApiUnreachable("down")
    await local_entry.runtime_data.local.async_refresh()
    eid = entity_id(hass, "switch", "mute_local")
    await hass.services.async_call("switch", "turn_on", {"entity_id": eid}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "unavailable"
