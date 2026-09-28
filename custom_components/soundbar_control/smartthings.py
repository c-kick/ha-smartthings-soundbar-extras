"""Isolate the dependency on the built-in SmartThings runtime API here."""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pysmartthings import SmartThingsError

from .const import DOMAIN, SOURCE_CAPABILITY

_LOGGER = logging.getLogger(__name__)


def attribute(device, capability: str, name: str) -> Any:
    value = device.status.get("main", {}).get(capability, {}).get(name)
    return getattr(value, "value", None)


def discover(hass) -> dict[str, dict]:
    """List soundbars from loaded HA SmartThings entries without cloud requests."""
    result = {}
    for entry in hass.config_entries.async_entries("smartthings"):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        data = getattr(entry, "runtime_data", None)
        for device_id, device in getattr(data, "devices", {}).items():
            caps = device.status.get("main", {})
            label = str(device.device.label or device.device.name)
            model = str(attribute(device, "ocf", "mnmo") or "")
            if not {"audioVolume", "execute"}.issubset(caps):
                continue
            if not (model.upper().startswith("HW-") or "soundbar" in label.lower()):
                continue
            result[f"{entry.entry_id}:{device_id}"] = {
                "parent_entry_id": entry.entry_id,
                "device_id": device_id,
                "name": label,
                "model": model,
            }
    return result


class SmartThingsAdapter:
    """Resolve the current parent on every call so integration reloads are safe."""

    def __init__(self, hass, parent_entry_id: str, device_id: str):
        self.hass = hass
        self.parent_entry_id = parent_entry_id
        self.device_id = device_id

    @property
    def parent(self):
        return self.hass.config_entries.async_get_entry(self.parent_entry_id)

    @property
    def device(self):
        parent = self.parent
        if parent is None or parent.state is not ConfigEntryState.LOADED:
            return None
        return getattr(getattr(parent, "runtime_data", None), "devices", {}).get(self.device_id)

    @property
    def client(self):
        return getattr(self.parent.runtime_data, "client", None) if self.device else None

    @property
    def capabilities(self) -> list[str]:
        device = self.device
        return sorted(device.status.get("main", {})) if device else []

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities

    def attribute(self, capability: str, name: str) -> Any:
        device = self.device
        return attribute(device, capability, name) if device else None

    async def online(self) -> bool | None:
        """Read current device health; None when it cannot be read.

        The parent's FullDevice.online is a snapshot from its own setup and is never
        updated afterwards, so it can be stale when this companion (re)binds.
        """
        client = self.client
        if client is None:
            return None
        try:
            async with asyncio.timeout(30):
                result = await client.get_device_health(self.device_id)
        except SmartThingsError, aiohttp.ClientError, TimeoutError, ValueError:
            return None
        return str(result.state).upper() == "ONLINE"

    def subscribe(self, on_source: Callable, on_health: Callable) -> list[Callable]:
        client = self.client
        if client is None:
            return []
        unsub = [client.add_device_availability_event_listener(self.device_id, on_health)]
        if self.has_capability(SOURCE_CAPABILITY):
            unsub.append(
                client.add_device_capability_event_listener(
                    self.device_id, "main", SOURCE_CAPABILITY, on_source
                )
            )
        return unsub

    async def command(self, capability: str, command: str, arguments: list) -> None:
        """Use the parent's refresh lock, enforce acceptance, never replay a POST."""
        refresh = getattr(self.client, "refresh_token_function", None)
        if not callable(refresh):
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="smartthings_unavailable"
            )
        try:
            async with asyncio.timeout(30):
                token = await refresh()
                async with async_get_clientsession(self.hass).post(
                    f"https://api.smartthings.com/v1/devices/{self.device_id}/commands",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "commands": [
                            {
                                "component": "main",
                                "capability": capability,
                                "command": command,
                                "arguments": arguments,
                            }
                        ]
                    },
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_failed"
            ) from err
        results = result.get("results") if isinstance(result, dict) else None
        if (
            not isinstance(results, list)
            or len(results) != 1
            or not isinstance(results[0], dict)
            or results[0].get("status") != "COMPLETED"
        ):
            _LOGGER.warning("SmartThings rejected %s.%s: %s", capability, command, result)
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="command_failed")
