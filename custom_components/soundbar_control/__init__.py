"""SmartThings Soundbar Extras: a companion to the built-in integration."""

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_CERT, CONF_HOST, CONF_USE_LOCAL, DOMAIN, PLATFORMS, SETTINGS
from .coordinator import LocalCoordinator, delete_local_issues
from .local_api import LocalSoundbarClient
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
    if entry.options.get(CONF_USE_LOCAL):
        client = LocalSoundbarClient(
            async_get_clientsession(hass), entry.options[CONF_HOST], entry.options[CONF_CERT]
        )
        runtime.local = LocalCoordinator(hass, entry, runtime, client)
    runtime.local_options = dict(entry.options)
    entry.runtime_data = runtime
    runtime.bind()
    entry.async_on_unload(runtime.close)
    entry.async_on_unload(runtime.adapter.parent.async_on_state_change(runtime.bind))
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if runtime.local is not None:
        # Never await local I/O during setup: cloud entities must not wait for it.
        entry.async_create_background_task(
            hass, runtime.local.async_refresh(), f"{DOMAIN} local first refresh"
        )
    return True


async def _async_options_updated(hass, entry: SoundbarConfigEntry):
    runtime = entry.runtime_data
    old, new = runtime.local_options, dict(entry.options)
    runtime.local_options = new
    if old == new:
        return  # a data-only update (e.g. reconfigure), which reloads by itself
    if {k: v for k, v in old.items() if k != CONF_HOST} == {
        k: v for k, v in new.items() if k != CONF_HOST
    }:
        # Only the address moved: switch the local connection in place, so cloud
        # entities are never interrupted.
        if runtime.local is not None:
            runtime.local.client.host = new[CONF_HOST]
            await runtime.local.async_request_refresh()
        return
    hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(hass, entry: SoundbarConfigEntry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass, entry: SoundbarConfigEntry):
    delete_local_issues(hass, entry.entry_id)


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
