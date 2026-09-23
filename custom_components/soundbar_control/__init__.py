"""SmartThings Soundbar Extras: a companion to the built-in integration."""

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS, SETTINGS
from .profiles import EXTRA_CONTROLS, has_q930d_profile
from .runtime import SoundbarRuntime

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
type SoundbarConfigEntry = ConfigEntry[SoundbarRuntime]


async def async_setup(hass, config):
    """Retain the v1 action, with explicit targeting for multiple soundbars."""

    async def handle_set(call):
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
            and (
                not call.data.get("device_id")
                or entry.data.get("device_id") == call.data["device_id"]
            )
        ]
        if len(entries) != 1:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="choose_device")
        await entries[0].runtime_data.set(call.data["setting"], call.data["enabled"])

    hass.services.async_register(
        DOMAIN,
        "set",
        handle_set,
        schema=vol.Schema(
            {
                vol.Required("setting"): vol.In(SETTINGS),
                vol.Required("enabled"): bool,
                vol.Optional("device_id"): str,
            }
        ),
    )
    return True


async def async_setup_entry(hass, entry: SoundbarConfigEntry):
    runtime = SoundbarRuntime(hass, entry)
    if runtime.adapter.parent is None:
        # A re-added SmartThings entry gets a new ID; retrying can never succeed.
        raise ConfigEntryError(translation_domain=DOMAIN, translation_key="parent_removed")
    if runtime.adapter.device is None:
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="parent_not_loaded")
    entry.runtime_data = runtime
    runtime.bind()
    entry.async_on_unload(runtime.close)
    entry.async_on_unload(runtime.adapter.parent.async_on_state_change(runtime.bind))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry: SoundbarConfigEntry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass, entry: SoundbarConfigEntry):
    """Enable the HW-Q930D audio controls once when upgrading from 2.0."""
    if entry.version != 2:
        return False
    if entry.minor_version < 2:
        settings = list(entry.data["settings"])
        if has_q930d_profile(entry.data["model"]):
            settings.extend(key for key in EXTRA_CONTROLS if key not in settings)
        hass.config_entries.async_update_entry(
            entry, minor_version=2, data={**entry.data, "settings": settings}
        )
    return True
