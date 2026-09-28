"""The Configure dialog: enabling, validating, pinning and disabling the local API."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir

from custom_components.soundbar_control.config_flow import validate_local
from custom_components.soundbar_control.const import DOMAIN
from custom_components.soundbar_control.coordinator import issue_id
from custom_components.soundbar_control.discovery import Advertised, discovered_soundbars

from .local_fake import GENERIC_ERROR, FakeSoundbar
from .test_integration import reconfigure, setup

VALIDATE = "custom_components.soundbar_control.config_flow.validate_local"


async def start(hass, entry):
    return await hass.config_entries.options.async_init(entry.entry_id)


async def test_enable_pins_certificate(hass, parent, entry, local_client, dependencies):
    await setup(hass, entry)
    result = await start(hass, entry)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"use_local_api": True}
    )
    assert result["step_id"] == "local"
    with patch(VALIDATE, return_value=("22_AV_HW-Q930D", "AA:BB")):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"host": "192.0.2.10", "poll_on": 5, "poll_off": 60}
        )
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"] == {
        "identifier": "22_AV_HW-Q930D",
        "fingerprint": "AA:BB",
    }
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        "use_local_api": True,
        "host": "192.0.2.10",
        "mac": None,
        "cert_sha256": "AA:BB",
        "poll_on": 5,
        "poll_off": 60,
        "media_player": True,
    }


async def test_media_player_can_be_switched_off(hass, parent, local_entry, dependencies):
    await setup(hass, local_entry)
    result = await start(hass, local_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"use_local_api": True}
    )
    with patch(VALIDATE, return_value=("22_AV_HW-Q930D", "AA:BB")):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"host": "192.0.2.10", "poll_on": 5, "poll_off": 60, "media_player": False},
        )
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert local_entry.options["media_player"] is False


async def test_discovered_host_stores_mac(hass, parent, entry, local_client, dependencies):
    await setup(hass, entry)
    discovered_soundbars(hass)["02:00:00:00:00:01"] = Advertised("192.0.2.10", "Q-Series Soundbar")
    result = await start(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"use_local_api": True}
    )
    with patch(VALIDATE, return_value=("22_AV_HW-Q930D", "AA:BB")):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"host": "192.0.2.10", "poll_on": 5, "poll_off": 60}
        )
    await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert entry.options["mac"] == "02:00:00:00:00:01"


@pytest.mark.parametrize("error", ["cannot_connect", "ip_control_disabled", "not_a_soundbar"])
async def test_validation_errors(hass, parent, entry, dependencies, error):
    await setup(hass, entry)
    result = await start(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"use_local_api": True}
    )
    with patch(VALIDATE, side_effect=ValueError(error)):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"host": " 192.0.2.99 ", "poll_on": 5, "poll_off": 60}
        )
    assert result["errors"] == {"base": error}
    assert entry.options == {}
    # The form re-shows what the user typed, not the stored or discovered host.
    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert defaults["host"] == "192.0.2.99"


async def test_disable_clears_options_and_issues(hass, parent, local_entry, dependencies):
    await setup(hass, local_entry)
    for kind in ("certificate_changed", "local_unreachable"):
        ir.async_create_issue(
            hass, DOMAIN, issue_id(kind, local_entry.entry_id), is_fixable=False,
            severity=ir.IssueSeverity.ERROR, translation_key=kind,
        )  # fmt: skip
    result = await start(hass, local_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"use_local_api": False}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert local_entry.options == {}
    registry = ir.async_get(hass)
    for kind in ("certificate_changed", "local_unreachable"):
        assert not registry.async_get_issue(DOMAIN, issue_id(kind, local_entry.entry_id))
    assert local_entry.runtime_data.local is None


async def test_resave_clears_issues(hass, parent, local_entry, dependencies):
    await setup(hass, local_entry)
    ir.async_create_issue(
        hass, DOMAIN, issue_id("certificate_changed", local_entry.entry_id), is_fixable=False,
        severity=ir.IssueSeverity.ERROR, translation_key="certificate_changed",
    )  # fmt: skip
    result = await start(hass, local_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"use_local_api": True}
    )
    with patch(VALIDATE, return_value=("22_AV_HW-Q930D", "CC:DD")):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"host": "192.0.2.10", "poll_on": 5, "poll_off": 60}
        )
    await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert not ir.async_get(hass).async_get_issue(
        DOMAIN, issue_id("certificate_changed", local_entry.entry_id)
    )


async def test_poll_change_reloads(hass, parent, local_entry, dependencies):
    await setup(hass, local_entry)
    before = local_entry.runtime_data
    hass.config_entries.async_update_entry(
        local_entry, options={**local_entry.options, "poll_on": 10}
    )
    await hass.async_block_till_done()
    assert local_entry.runtime_data is not before
    assert local_entry.runtime_data.local.update_interval.total_seconds() == 10


async def test_host_only_change_does_not_reload(
    hass, parent, local_entry, local_client, dependencies
):
    await setup(hass, local_entry)
    before = local_entry.runtime_data
    hass.config_entries.async_update_entry(
        local_entry, options={**local_entry.options, "host": "192.0.2.99"}
    )
    await hass.async_block_till_done()
    assert local_entry.runtime_data is before
    assert local_client.host == "192.0.2.99"


async def test_remove_entry_deletes_issues(hass, parent, local_entry, dependencies):
    await setup(hass, local_entry)
    ir.async_create_issue(
        hass, DOMAIN, issue_id("local_unreachable", local_entry.entry_id), is_fixable=False,
        severity=ir.IssueSeverity.WARNING, translation_key="local_unreachable",
    )  # fmt: skip
    await hass.config_entries.async_remove(local_entry.entry_id)
    assert not ir.async_get(hass).async_get_issue(
        DOMAIN, issue_id("local_unreachable", local_entry.entry_id)
    )


async def test_validate_local_against_fake(hass, tmp_path, socket_enabled):
    bar = FakeSoundbar(tmp_path)
    await bar.start()
    try:
        identifier, sha = await validate_local(hass, "127.0.0.1", port=bar.port)
        assert identifier == "22_AV_HW-Q930D"
        assert sha == bar.sha256
        bar.state["identifier"] = "SOMETHING_ELSE"
        with pytest.raises(ValueError, match="not_a_soundbar"):
            await validate_local(hass, "127.0.0.1", port=bar.port)
    finally:
        await bar.stop()


async def test_validate_local_refused(hass, socket_enabled):
    with pytest.raises(ValueError, match="ip_control_disabled"):
        await validate_local(hass, "127.0.0.1", port=1)


async def test_validate_local_token_rejected(hass, tmp_path, socket_enabled):
    bar = FakeSoundbar(tmp_path)
    await bar.start()
    try:
        bar.raw["createAccessToken"] = GENERIC_ERROR
        with pytest.raises(ValueError, match="ip_control_disabled"):
            await validate_local(hass, "127.0.0.1", port=bar.port)
    finally:
        await bar.stop()


async def test_validate_local_garbled_reply_is_not_a_soundbar(hass, tmp_path, socket_enabled):
    bar = FakeSoundbar(tmp_path)
    await bar.start()
    try:
        bar.raw["getIdentifier"] = {"jsonrpc": "2.0", "result": "x"}
        with pytest.raises(ValueError, match="not_a_soundbar"):
            await validate_local(hass, "127.0.0.1", port=bar.port)
    finally:
        await bar.stop()


async def test_reconfigure_with_local_api_reloads(hass, parent, local_entry, dependencies, caplog):
    await setup(hass, local_entry)
    await hass.async_block_till_done(wait_background_tasks=True)
    before = local_entry.runtime_data
    result = await reconfigure(hass, local_entry, ["nightmode"])
    await hass.async_block_till_done(wait_background_tasks=True)
    assert result["reason"] == "reconfigure_successful"
    assert local_entry.data["settings"] == ["nightmode"]
    assert local_entry.state is ConfigEntryState.LOADED
    assert local_entry.runtime_data is not before  # reloaded
    assert local_entry.runtime_data.local is not None
    assert "update listener" not in caplog.text
