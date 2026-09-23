"""AirPlay discovery: cache, certificate-checked address moves, never new entries."""

import asyncio
from ipaddress import ip_address
from unittest.mock import AsyncMock, patch

from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.soundbar_control.const import DOMAIN
from custom_components.soundbar_control.discovery import (
    RECHECK_AFTER,
    async_check_address,
    discovered_soundbars,
)
from custom_components.soundbar_control.local_api import LocalApiUnreachable

from .test_integration import setup

FETCH = "custom_components.soundbar_control.discovery.fetch_certificate_sha256"


def airplay(host="192.0.2.20", mac="02:00:00:00:00:01", model="HW-Q930D"):
    return ZeroconfServiceInfo(
        ip_address=ip_address(host),
        ip_addresses=[ip_address(host)],
        port=7000,
        hostname="q-series.local.",
        type="_airplay._tcp.local.",
        name="Q-Series Soundbar._airplay._tcp.local.",
        properties={"deviceid": mac, "manufacturer": "Samsung", "model": model},
    )


async def discover(hass, info):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=info
    )


async def test_discovery_only_caches(hass, parent, dependencies):
    result = await discover(hass, airplay())
    assert result["type"] == "abort"
    assert result["reason"] == "not_supported"
    assert hass.config_entries.async_entries(DOMAIN) == []
    assert discovered_soundbars(hass)["02:00:00:00:00:01"].host == "192.0.2.20"


async def test_tv_is_ignored(hass, parent, dependencies):
    await discover(hass, airplay(model="QE65S95D"))
    assert discovered_soundbars(hass) == {}


async def test_matching_certificate_moves_host_without_reload(
    hass, parent, local_entry, local_client, dependencies
):
    await setup(hass, local_entry)
    before = local_entry.runtime_data
    with patch(FETCH, AsyncMock(return_value="AA:BB")):
        await discover(hass, airplay())
        await hass.async_block_till_done(wait_background_tasks=True)
    assert local_entry.options["host"] == "192.0.2.20"
    assert local_client.host == "192.0.2.20"
    assert local_entry.runtime_data is before  # no reload


async def test_mismatch_changes_nothing(hass, parent, local_entry, dependencies):
    await setup(hass, local_entry)
    with patch(FETCH, AsyncMock(return_value="EE:FF")):
        await discover(hass, airplay())
        await hass.async_block_till_done(wait_background_tasks=True)
    assert local_entry.options["host"] == "192.0.2.10"


async def test_unreachable_candidate_changes_nothing(hass, parent, local_entry, dependencies):
    await setup(hass, local_entry)
    with patch(FETCH, AsyncMock(side_effect=LocalApiUnreachable("no"))):
        assert not await async_check_address(hass, local_entry, "192.0.2.20")
    assert local_entry.options["host"] == "192.0.2.10"


async def test_repeated_advertisements_checked_once(hass, parent, local_entry, dependencies):
    await setup(hass, local_entry)
    now = [1000.0]
    fetch = AsyncMock(return_value="EE:FF")
    with patch(FETCH, fetch):
        for _ in range(5):
            await async_check_address(hass, local_entry, "192.0.2.20", clock=lambda: now[0])
        assert fetch.await_count == 1
        now[0] += RECHECK_AFTER + 1
        await async_check_address(hass, local_entry, "192.0.2.20", clock=lambda: now[0])
        assert fetch.await_count == 2


async def test_concurrent_checks_coalesce(hass, parent, local_entry, dependencies):
    await setup(hass, local_entry)
    gate = asyncio.Event()

    async def slow(host, port=1516):
        await gate.wait()
        return "EE:FF"

    with patch(FETCH, side_effect=slow) as fetch:
        first = hass.async_create_task(async_check_address(hass, local_entry, "192.0.2.20"))
        await asyncio.sleep(0)
        assert not await async_check_address(hass, local_entry, "192.0.2.30")
        gate.set()
        await first
    assert fetch.await_count == 1


async def test_current_host_is_not_checked(hass, parent, local_entry, dependencies):
    await setup(hass, local_entry)
    with patch(FETCH, AsyncMock()) as fetch:
        assert not await async_check_address(hass, local_entry, "192.0.2.10")
    fetch.assert_not_awaited()
