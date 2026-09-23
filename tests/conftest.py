"""Real HA lifecycle with the parent SmartThings integration's real runtime types."""

from unittest.mock import AsyncMock, patch

import orjson
import pytest
from homeassistant.components.smartthings import FullDevice, SmartThingsData
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pysmartthings import SmartThings
from pysmartthings.models import Attribute, Capability, Device, DeviceHealth, Status
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.soundbar_control.const import DOMAIN

DEVICE = "test-soundbar-device"
LOCATION = "test-location"


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


def health(state: str = "ONLINE") -> DeviceHealth:
    return DeviceHealth.from_dict(
        {"deviceId": DEVICE, "state": state, "lastUpdatedDate": "2026-09-23T00:00:00Z"}
    )


def make_client(hass) -> SmartThings:
    client = SmartThings(session=async_get_clientsession(hass))

    async def refresh():
        return "test-token"

    client.refresh_token_function = refresh
    # The only read the companion makes; never let tests reach the network.
    client.get_device_health = AsyncMock(return_value=health())
    return client


def make_device(device_id: str = DEVICE, label: str = "Test Soundbar") -> FullDevice:
    device = Device.from_dict(
        {
            "deviceId": device_id,
            "name": "Soundbar",
            "label": label,
            "locationId": LOCATION,
            "type": "OCF",
            "components": {},
        }
    )
    status = {
        "main": {
            Capability.AUDIO_VOLUME: {},
            Capability.EXECUTE: {},
            Capability.OCF: {Attribute("mnmo"): Status("HW-Q930D")},
            Capability("samsungvd.audioInputSource"): {Attribute("inputSource"): Status("D.IN")},
        }
    }
    return FullDevice(device=device, status=status, online=True)


def fire(client: SmartThings, event_type: str, device_id: str = DEVICE, **event) -> None:
    """Feed one raw event through pysmartthings' own parsing and dispatch."""
    key = {"DEVICE_EVENT": "deviceEvent", "DEVICE_HEALTH_EVENT": "deviceHealthEvent"}[event_type]
    body = {"deviceId": device_id, "locationId": LOCATION, **event}
    if event_type == "DEVICE_EVENT":
        body |= {"eventId": "e", "ownerId": "o", "componentId": "main"}
    payload = {"eventTime": 0, "eventType": event_type, key: body}
    client._dispatch_event(event_type, orjson.dumps(payload).decode())


@pytest.fixture
async def parent(hass):
    entry = MockConfigEntry(domain="smartthings", state=ConfigEntryState.LOADED)
    entry.add_to_hass(hass)
    entry.runtime_data = SmartThingsData(
        devices={DEVICE: make_device()}, scenes={}, rooms={}, client=make_client(hass)
    )
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("smartthings", DEVICE)},
        name="Test Soundbar",
        manufacturer="Samsung",
    )
    yield entry
    entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


@pytest.fixture
def entry(hass, parent):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=2,
        unique_id=DEVICE,
        data={
            "parent_entry_id": parent.entry_id,
            "device_id": DEVICE,
            "name": "Test Soundbar",
            "model": "HW-Q930D",
            "settings": ["nightmode", "voiceamplifier", "bassboost"],
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def dependencies():
    with (
        patch("homeassistant.config_entries.async_process_deps_reqs"),
        patch("homeassistant.setup.async_process_deps_reqs"),
    ):
        yield


@pytest.fixture
def local_client():
    """Replace the transport with an in-memory fake for integration tests."""
    from .local_fake import FakeLocalClient

    fake = FakeLocalClient()

    def build(session, host, cert_sha256, port=1516):
        fake.host = host
        return fake

    with patch("custom_components.soundbar_control.LocalSoundbarClient", build):
        yield fake


@pytest.fixture
def local_entry(hass, entry, local_client):
    """The standard entry with the local API enabled."""
    hass.config_entries.async_update_entry(
        entry,
        options={
            "use_local_api": True,
            "host": "192.0.2.10",
            "mac": "02:00:00:00:00:01",
            "cert_sha256": "AA:BB",
            "poll_on": 5,
            "poll_off": 60,
        },
    )
    return entry
