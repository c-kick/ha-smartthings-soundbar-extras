"""Local polling: isolation from the cloud, intervals, and repair issues."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.soundbar_control.const import DOMAIN
from custom_components.soundbar_control.coordinator import UNREACHABLE_AFTER, issue_id
from custom_components.soundbar_control.local_api import (
    LocalApiCertificateChanged,
    LocalApiUnreachable,
)

from .conftest import DEVICE, fire
from .local_fake import status
from .test_integration import setup


def night_mode(hass):
    return er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"{DEVICE}_nightmode")


async def ready(hass, entry):
    """Set up and let the background first refresh finish before the test acts."""
    await setup(hass, entry)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_setup_does_not_wait_for_local(hass, parent, local_entry, local_client, dependencies):
    local_client.gate = asyncio.Event()  # the soundbar never answers
    async with asyncio.timeout(5):
        await setup(hass, local_entry)
    assert local_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(night_mode(hass)).state != "unavailable"
    assert await hass.config_entries.async_unload(local_entry.entry_id)
    # Would hang until the timeout if unload left the first refresh running.
    async with asyncio.timeout(5):
        await hass.async_block_till_done(wait_background_tasks=True)


async def test_first_refresh_runs_in_background(
    hass, parent, local_entry, local_client, dependencies
):
    await ready(hass, local_entry)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert local_entry.runtime_data.local.data.codec == "DTS"


async def test_local_off_creates_no_coordinator(hass, parent, entry, dependencies):
    await setup(hass, entry)
    assert entry.runtime_data.local is None


async def test_interval_follows_power(hass, parent, local_entry, local_client, dependencies):
    await ready(hass, local_entry)
    await hass.async_block_till_done(wait_background_tasks=True)
    local = local_entry.runtime_data.local
    assert local.update_interval == timedelta(seconds=5)
    local_client.value = status(power=False)
    await local.async_refresh()
    assert local.update_interval == timedelta(seconds=60)
    local_client.value = status(power=None, failed=frozenset({"power"}))
    await local.async_refresh()
    assert local.update_interval == timedelta(seconds=5)


async def test_local_failure_leaves_cloud_available(
    hass, parent, local_entry, local_client, dependencies
):
    await ready(hass, local_entry)
    local_client.error = LocalApiUnreachable("down")
    await local_entry.runtime_data.local.async_refresh()
    assert not local_entry.runtime_data.local.last_update_success
    assert local_entry.runtime_data.available
    assert hass.states.get(night_mode(hass)).state != "unavailable"


async def test_certificate_change_raises_issue(
    hass, parent, local_entry, local_client, dependencies
):
    await ready(hass, local_entry)
    local_client.error = LocalApiCertificateChanged("changed")
    await local_entry.runtime_data.local.async_refresh()
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, issue_id("certificate_changed", local_entry.entry_id))
    local_client.error = None
    await local_entry.runtime_data.local.async_refresh()
    assert not registry.async_get_issue(
        DOMAIN, issue_id("certificate_changed", local_entry.entry_id)
    )


async def test_unreachable_issue_needs_time_and_smartthings_online(
    hass, parent, local_entry, local_client, dependencies
):
    await ready(hass, local_entry)
    local = local_entry.runtime_data.local
    now = [1000.0]
    local._clock = lambda: now[0]
    local_client.error = LocalApiUnreachable("down")
    unreachable = issue_id("local_unreachable", local_entry.entry_id)
    registry = ir.async_get(hass)

    await local.async_refresh()
    now[0] += UNREACHABLE_AFTER - 1
    await local.async_refresh()
    assert not registry.async_get_issue(DOMAIN, unreachable)

    now[0] += 2
    await local.async_refresh()
    assert registry.async_get_issue(DOMAIN, unreachable)

    local_client.error = None
    await local.async_refresh()
    assert not registry.async_get_issue(DOMAIN, unreachable)


async def test_unreachable_issue_needs_smartthings_online(
    hass, parent, local_entry, local_client, dependencies
):
    await ready(hass, local_entry)
    local = local_entry.runtime_data.local
    now = [1000.0]
    local._clock = lambda: now[0]
    fire(parent.runtime_data.client, "DEVICE_HEALTH_EVENT", status="OFFLINE")
    local_client.error = LocalApiUnreachable("unplugged")
    await local.async_refresh()
    now[0] += UNREACHABLE_AFTER * 4
    await local.async_refresh()
    assert not ir.async_get(hass).async_get_issue(
        DOMAIN, issue_id("local_unreachable", local_entry.entry_id)
    )


async def test_unreachable_window_starts_when_smartthings_is_online(
    hass, parent, local_entry, local_client, dependencies
):
    """An unplugged soundbar that comes back doesn't count its offline failures."""
    await ready(hass, local_entry)
    local = local_entry.runtime_data.local
    now = [1000.0]
    local._clock = lambda: now[0]
    unreachable = issue_id("local_unreachable", local_entry.entry_id)
    registry = ir.async_get(hass)
    client = parent.runtime_data.client
    fire(client, "DEVICE_HEALTH_EVENT", status="OFFLINE")
    local_client.error = LocalApiUnreachable("unplugged")
    for _ in range(4):
        await local.async_refresh()
        now[0] += UNREACHABLE_AFTER

    fire(client, "DEVICE_HEALTH_EVENT", status="ONLINE")
    await local.async_refresh()
    assert not registry.async_get_issue(DOMAIN, unreachable)

    now[0] += UNREACHABLE_AFTER
    await local.async_refresh()
    assert registry.async_get_issue(DOMAIN, unreachable)


async def test_certificate_failure_resets_unreachable_window(
    hass, parent, local_entry, local_client, dependencies
):
    await ready(hass, local_entry)
    local = local_entry.runtime_data.local
    now = [1000.0]
    local._clock = lambda: now[0]
    local_client.error = LocalApiUnreachable("down")
    await local.async_refresh()
    now[0] += UNREACHABLE_AFTER
    local_client.error = LocalApiCertificateChanged("changed")
    await local.async_refresh()
    local_client.error = LocalApiUnreachable("down")
    await local.async_refresh()
    assert not ir.async_get(hass).async_get_issue(
        DOMAIN, issue_id("local_unreachable", local_entry.entry_id)
    )


async def test_corrupt_local_options_leave_cloud_setup_intact(
    hass, parent, entry, dependencies, caplog
):
    hass.config_entries.async_update_entry(
        entry,
        options={
            "use_local_api": True,
            "host": "192.0.2.10",
            "cert_sha256": "not-hex",
            "poll_on": 5,
            "poll_off": 60,
        },
    )
    await ready(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.local is None
    assert hass.states.get(night_mode(hass)).state != "unavailable"
    logged = " ".join(r.getMessage() for r in caplog.records if r.levelno > logging.DEBUG)
    assert "local API options are invalid" in logged
    assert "192.0.2.10" not in logged
    assert "not-hex" not in logged
