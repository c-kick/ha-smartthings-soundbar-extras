"""End-to-end entity lifecycle, migration and assumed-state contracts."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.soundbar_control.const import DOMAIN
from custom_components.soundbar_control.diagnostics import async_get_config_entry_diagnostics

from .conftest import DEVICE, fire, make_client, make_device


async def setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_native_entities_state_and_failures(hass, parent, entry, dependencies):
    await setup(hass, entry)
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("switch", DOMAIN, f"{DEVICE}_nightmode")
    state = hass.states.get(entity_id)
    assert state.state == "unknown"
    assert state.attributes["assumed_state"] is True
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 5
    devices = dr.async_get(hass)
    parent_device = devices.async_get_device_by_identifier(("smartthings", DEVICE), parent.entry_id)
    companion = devices.async_get_device_by_identifier((DOMAIN, DEVICE), entry.entry_id)
    assert companion.via_device_id == parent_device.id
    with patch.object(entry.runtime_data.adapter, "command", new_callable=AsyncMock) as command:
        await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
        assert hass.states.get(entity_id).state == "on"
        command.assert_awaited_once()
        command.side_effect = HomeAssistantError("HTTP 401")
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "switch", "turn_off", {"entity_id": entity_id}, blocking=True
            )
        assert hass.states.get(entity_id).state == "on"
    runtime = entry.runtime_data
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not runtime.listeners


async def test_parent_reload_and_events(hass, parent, entry, dependencies):
    await setup(hass, entry)
    runtime = entry.runtime_data
    old_client = parent.runtime_data.client
    fire(old_client, "DEVICE_EVENT", capability="samsungvd.audioInputSource",
         attribute="inputSource", value="HDMI1")  # fmt: skip
    assert runtime.source == "HDMI1"
    fire(old_client, "DEVICE_HEALTH_EVENT", status="OFFLINE")
    assert not runtime.available
    fire(old_client, "DEVICE_HEALTH_EVENT", status="ONLINE")
    assert runtime.available
    fire(old_client, "DEVICE_HEALTH_EVENT", status="UNHEALTHY")
    assert not runtime.available
    fire(old_client, "DEVICE_HEALTH_EVENT", device_id="another-device", status="ONLINE")
    assert not runtime.available

    parent.mock_state(hass, ConfigEntryState.UNLOAD_IN_PROGRESS)
    assert not runtime.available
    # The parent reloads with a new client and fresh device status.
    new_client = make_client(hass)
    parent.runtime_data = type(parent.runtime_data)(
        devices={DEVICE: make_device()}, scenes={}, rooms={}, client=new_client
    )
    parent.mock_state(hass, ConfigEntryState.LOADED)
    assert runtime.available
    assert runtime.source == "D.IN"
    fire(old_client, "DEVICE_HEALTH_EVENT", status="OFFLINE")
    assert runtime.available
    fire(new_client, "DEVICE_HEALTH_EVENT", status="OFFLINE")
    assert not runtime.available
    await hass.config_entries.async_unload(entry.entry_id)


async def test_source_button_does_not_invent_source(hass, parent, entry, dependencies):
    await setup(hass, entry)
    registry = er.async_get(hass)
    button = registry.async_get_entity_id("button", DOMAIN, f"{DEVICE}_next_source")
    with patch.object(entry.runtime_data.adapter, "command", new_callable=AsyncMock) as command:
        await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
        command.assert_awaited_once_with("samsungvd.audioInputSource", "setNextInputSource", [])
    assert entry.runtime_data.source == "D.IN"


async def test_diagnostics_exclude_credentials_and_identifiers(hass, parent, entry, dependencies):
    await setup(hass, entry)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert DEVICE not in str(diagnostics)
    assert parent.entry_id not in str(diagnostics)
    assert "test-token" not in str(diagnostics)


async def test_local_diagnostics_exclude_address_and_pin(hass, parent, local_entry, dependencies):
    await setup(hass, local_entry)
    await hass.async_block_till_done(wait_background_tasks=True)
    diagnostics = await async_get_config_entry_diagnostics(hass, local_entry)
    local = diagnostics["local"]
    assert local["enabled"] is True
    assert local["cert_pinned"] is True
    assert local["poll_on"] == 5
    assert local["status"]["codec"] == "DTS"
    assert local["status"]["failed"] == []
    text = str(diagnostics)
    for secret in ("192.0.2.10", "02:00:00", "AA:BB"):
        assert secret not in text


async def test_flow_selection_and_duplicate(hass, parent, dependencies):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device": f"{parent.entry_id}:{DEVICE}"}
    )
    assert result["step_id"] == "features"
    with patch("custom_components.soundbar_control.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"settings": ["nightmode"]}
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"]["settings"] == ["nightmode"]
    second = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    second = await hass.config_entries.flow.async_configure(
        second["flow_id"], {"device": f"{parent.entry_id}:{DEVICE}"}
    )
    assert second["reason"] == "already_configured"


async def test_flow_without_parent(hass, dependencies):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["reason"] == "no_soundbars"


async def test_reconfigure_controls(hass, parent, entry, dependencies):
    await setup(hass, entry)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    assert result["step_id"] == "features"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"settings": ["nightmode"]}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["settings"] == ["nightmode"]
    assert entry.state is ConfigEntryState.LOADED


async def reconfigure(hass, entry, settings):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"settings": settings}
    )
    await hass.async_block_till_done()
    return result


async def test_reconfigure_reloads_without_usage_warning(hass, parent, entry, dependencies, caplog):
    await setup(hass, entry)
    before = entry.runtime_data
    result = await reconfigure(hass, entry, ["nightmode"])
    assert result["reason"] == "reconfigure_successful"
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not before  # reloaded
    assert "update listener" not in caplog.text


async def test_multiple_soundbars_require_explicit_service_target(
    hass, parent, entry, dependencies
):
    second_id = "second-test-soundbar"
    parent.runtime_data.devices[second_id] = make_device(second_id, "Second Soundbar")
    second = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id=second_id,
        data={**entry.data, "device_id": second_id, "name": "Second Soundbar"},
    )
    second.add_to_hass(hass)
    await setup(hass, entry)
    # Initial domain setup loads both already-registered entries.
    assert second.state is ConfigEntryState.LOADED
    with (
        patch.object(
            entry.runtime_data.adapter, "command", new_callable=AsyncMock
        ) as first_command,
        patch.object(
            second.runtime_data.adapter, "command", new_callable=AsyncMock
        ) as second_command,
    ):
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN, "set", {"setting": "nightmode", "enabled": True}, blocking=True
            )
        first_command.assert_not_called()
        second_command.assert_not_called()
        await hass.services.async_call(
            DOMAIN,
            "set",
            {"setting": "nightmode", "enabled": True, "device_id": second_id},
            blocking=True,
        )
        first_command.assert_not_called()
        second_command.assert_awaited_once()
        assert entry.runtime_data.states.get("nightmode") is None
        assert second.runtime_data.states["nightmode"] is True


async def test_unavailable_parent_defers_setup(hass, parent, entry, dependencies):
    parent.mock_state(hass, ConfigEntryState.NOT_LOADED)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_removed_parent_is_a_permanent_error(hass, parent, entry, dependencies):
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "parent_entry_id": "deleted-smartthings-entry"}
    )
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert "no longer exists" in entry.reason


async def test_unknown_major_version_is_not_migrated(hass, parent, dependencies):
    entry = MockConfigEntry(domain=DOMAIN, version=1, data={})
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.MIGRATION_ERROR
