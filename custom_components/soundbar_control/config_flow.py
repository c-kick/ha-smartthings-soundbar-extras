"""Select a soundbar already connected through Home Assistant SmartThings."""

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers import selector

from .const import DOMAIN
from .profiles import available_controls, has_q930d_profile
from .smartthings import discover


class SoundbarControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """No additional account, token, or network address required."""

    VERSION = 2
    MINOR_VERSION = 2

    async def async_step_reconfigure(self, user_input=None):
        self._reconfigure_entry = self._get_reconfigure_entry()
        self._selected = dict(self._reconfigure_entry.data)
        return await self.async_step_features(user_input)

    async def async_step_user(self, user_input=None):
        devices = discover(self.hass)
        if not devices:
            return self.async_abort(reason="no_soundbars")
        errors = {}
        if user_input is not None:
            device = devices.get(user_input["device"])
            if device is None:
                errors["base"] = "device_unavailable"
            else:
                await self.async_set_unique_id(device["device_id"])
                self._abort_if_unique_id_configured()
                self._selected = device
                return await self.async_step_features()
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("device"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {
                                    "value": key,
                                    "label": f"{value['name']} ({value['model'] or 'Samsung'})",
                                }
                                for key, value in devices.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_features(self, user_input=None):
        controls = available_controls(self._selected["model"])
        if user_input is not None:
            if not set(user_input.get("settings", [])).issubset(controls):
                return self.async_abort(reason="invalid_settings")
            if reconfigure_entry := getattr(self, "_reconfigure_entry", None):
                return self.async_update_reload_and_abort(
                    reconfigure_entry, data_updates={"settings": user_input.get("settings", [])}
                )
            return self.async_create_entry(
                title=self._selected["name"],
                data={**self._selected, "settings": user_input.get("settings", [])},
            )
        defaults = self._selected.get(
            "settings", (list(controls) if has_q930d_profile(self._selected["model"]) else [])
        )
        return self.async_show_form(
            step_id="features",
            data_schema=vol.Schema(
                {
                    vol.Optional("settings", default=defaults): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(controls), multiple=True, translation_key="settings"
                        )
                    )
                }
            ),
        )
