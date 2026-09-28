"""Select a soundbar already connected through Home Assistant SmartThings."""

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import (
    CONF_CERT,
    CONF_HOST,
    CONF_MAC,
    CONF_MEDIA_PLAYER,
    CONF_POLL_OFF,
    CONF_POLL_ON,
    CONF_USE_LOCAL,
    DEFAULT_POLL_OFF,
    DEFAULT_POLL_ON,
    DOMAIN,
)
from .coordinator import delete_local_issues
from .discovery import async_check_address, discovered_soundbars, remember
from .local_api import (
    LOCAL_PORT,
    LocalApiException,
    LocalApiRefused,
    LocalApiTokenRejected,
    LocalApiUnreachable,
    LocalSoundbarClient,
    fetch_certificate_sha256,
)
from .profiles import available_controls, has_q930d_profile
from .smartthings import discover


class SoundbarControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """No additional account, token, or network address required."""

    VERSION = 2
    MINOR_VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LocalApiOptionsFlow()

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo):
        """Remember advertised soundbars; never create entries or discovery cards."""
        properties = {str(k).lower(): v for k, v in discovery_info.properties.items()}
        mac = str(properties.get("deviceid", "")).lower()
        model = str(properties.get("model", "")).upper()
        host = next((str(ip) for ip in discovery_info.ip_addresses if ip.version == 4), None)
        if mac and host and model.startswith("HW-"):
            remember(self.hass, mac, host, discovery_info.name.split(".")[0])
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if entry.options.get(CONF_MAC) == mac:
                    entry.async_create_background_task(
                        self.hass,
                        async_check_address(self.hass, entry, host),
                        f"{DOMAIN} address check",
                    )
        return self.async_abort(reason="not_supported")

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
                # The update listener schedules the reload (see __init__.py).
                return self.async_update_and_abort(
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


async def validate_local(hass, host: str, port: int = LOCAL_PORT) -> tuple[str, str]:
    """Fetch and pin the certificate, then prove it's a soundbar. Raises ValueError(key)."""
    try:
        sha = await fetch_certificate_sha256(host, port)
        client = LocalSoundbarClient(async_get_clientsession(hass), host, sha, port=port)
        identifier = await client.identify()
    except LocalApiRefused as err:
        raise ValueError("ip_control_disabled") from err
    except LocalApiUnreachable as err:
        raise ValueError("cannot_connect") from err
    except LocalApiTokenRejected as err:
        raise ValueError("ip_control_disabled") from err
    except LocalApiException as err:
        # Answered, but not like a soundbar: a garbled or rejected reply, or the
        # certificate changed mid-flow.
        raise ValueError("not_a_soundbar") from err
    if "HW-" not in identifier.upper():
        raise ValueError("not_a_soundbar")
    return identifier, sha


def _seconds(minimum: int, maximum: int) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            unit_of_measurement="s",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


class LocalApiOptionsFlow(OptionsFlow):
    """Configure -> Use local API -> address and polling -> trust the certificate."""

    def __init__(self):
        self._pending: dict = {}
        self._identifier = ""

    async def async_step_init(self, user_input=None):
        options = self.config_entry.options
        if user_input is not None:
            if not user_input[CONF_USE_LOCAL]:
                delete_local_issues(self.hass, self.config_entry.entry_id)
                return self.async_create_entry(data={})
            return await self.async_step_local()
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required(CONF_USE_LOCAL, default=options.get(CONF_USE_LOCAL, False)): bool}
            ),
        )

    async def async_step_local(self, user_input=None):
        options = self.config_entry.options
        discovered = discovered_soundbars(self.hass)
        errors = {}
        host = None
        if user_input is not None and CONF_HOST in user_input:
            host = str(user_input[CONF_HOST]).strip()
            try:
                self._identifier, sha = await validate_local(self.hass, host)
            except ValueError as err:
                errors["base"] = err.args[0]
            else:
                mac = next((m for m, ad in discovered.items() if ad.host == host), None)
                if mac is None and host == options.get(CONF_HOST):
                    mac = options.get(CONF_MAC)
                self._pending = {
                    CONF_USE_LOCAL: True,
                    CONF_HOST: host,
                    CONF_MAC: mac,
                    CONF_CERT: sha,
                    CONF_POLL_ON: int(user_input[CONF_POLL_ON]),
                    CONF_POLL_OFF: int(user_input[CONF_POLL_OFF]),
                    CONF_MEDIA_PLAYER: bool(user_input[CONF_MEDIA_PLAYER]),
                }
                return await self.async_step_confirm()
        # After a validation error, re-show the host the user typed.
        default_host = (
            host or options.get(CONF_HOST) or next((ad.host for ad in discovered.values()), "")
        )
        return self.async_show_form(
            step_id="local",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=default_host): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": ad.host, "label": f"{ad.host} – {ad.name}"}
                                for ad in discovered.values()
                            ],
                            custom_value=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_POLL_ON, default=options.get(CONF_POLL_ON, DEFAULT_POLL_ON)
                    ): _seconds(2, 60),
                    vol.Required(
                        CONF_POLL_OFF, default=options.get(CONF_POLL_OFF, DEFAULT_POLL_OFF)
                    ): _seconds(10, 600),
                    vol.Required(
                        CONF_MEDIA_PLAYER, default=options.get(CONF_MEDIA_PLAYER, True)
                    ): bool,
                }
            ),
        )

    async def async_step_confirm(self, user_input=None):
        if user_input is not None:
            delete_local_issues(self.hass, self.config_entry.entry_id)
            return self.async_create_entry(data=self._pending)
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "identifier": self._identifier,
                "fingerprint": self._pending[CONF_CERT],
            },
        )
