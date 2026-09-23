"""Per-soundbar state and lifecycle. Advanced audio remains explicitly assumed."""

import asyncio
import time

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN, PREFIX, SOURCE_CAPABILITY
from .profiles import CHANNELS, LEVELS, SOUND_MODES, available_controls, valid_level
from .smartthings import SmartThingsAdapter


class SoundbarRuntime:
    """Serialize commands and reconnect listeners when the parent reloads."""

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.adapter = SmartThingsAdapter(
            hass, entry.data["parent_entry_id"], entry.data["device_id"]
        )
        self.states: dict[str, bool | str | int | None] = {}
        self.listeners = set()
        self._unsub = []
        self._lock = asyncio.Lock()
        self.online = False
        self.source = None
        # Bumped by every availability update, so a slow health read never
        # overwrites a newer event or a rebind.
        self._health_version = 0
        # Optional local API (see coordinator.py); None when disabled.
        self.local = None
        self.local_options: dict = {}
        # When the last cloud sound-mode command was accepted. A local reading only
        # confirms the mode if it started later.
        self.sound_mode_commanded = 0.0

    @property
    def available(self):
        return self.adapter.device is not None and self.online

    def enabled(self, key: str) -> bool:
        """Selected by the user and supported by this model's profile."""
        return key in self.entry.data["settings"] and key in available_controls(
            self.entry.data["model"]
        )

    @callback
    def notify(self):
        for listener in tuple(self.listeners):
            listener()

    @callback
    def bind(self):
        self.close()
        device = self.adapter.device
        self._health_version += 1
        self.online = bool(device and device.online)
        self.source = self.adapter.attribute(SOURCE_CAPABILITY, "inputSource")
        self._unsub = self.adapter.subscribe(self._source_event, self._health_event)
        self.notify()
        if device is not None:
            self.entry.async_create_background_task(
                self.hass, self._refresh_health(self._health_version), f"{DOMAIN} health"
            )

    async def _refresh_health(self, version: int):
        online = await self.adapter.online()
        if online is not None and version == self._health_version:
            self.online = online
            self.notify()

    @callback
    def close(self):
        for unsub in self._unsub:
            unsub()
        self._unsub = []

    @callback
    def _source_event(self, event):
        if event.attribute == "inputSource":
            self.source = event.value
            self.notify()

    @callback
    def _health_event(self, event):
        self._health_version += 1
        self.online = str(event.status).upper() == "ONLINE"
        self.notify()

    async def set(self, setting: str, enabled: bool):
        self._require(setting)
        await self._execute("advancedaudio", {f"{PREFIX}{setting}": int(enabled)}, setting, enabled)

    async def next_source(self):
        await self._send(SOURCE_CAPABILITY, "setNextInputSource", [])

    async def set_sound_mode(self, mode: str):
        if mode not in SOUND_MODES:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_sound_mode"
            )
        self._require("sound_mode")
        await self._execute(
            "soundmode", {f"{PREFIX}soundmode": SOUND_MODES[mode]}, "sound_mode", mode
        )

    async def set_level(self, key: str, value: float):
        if key not in LEVELS or not valid_level(value):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_level")
        self._require(key)
        level = int(value)
        if key == "woofer_level":
            resource = "woofer"
            payload = {f"{PREFIX}woofer": level}
        else:
            resource = "channelVolume"
            # Change only this channel. Never send guessed values for its neighbors.
            payload = {f"{PREFIX}channelVolume": [{"name": CHANNELS[key], "value": level}]}
        await self._execute(resource, payload, key, level)

    def _require(self, key: str):
        # Also guards the legacy action, which bypasses the entity platforms.
        if not self.enabled(key):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="setting_disabled"
            )

    async def _execute(self, resource: str, payload: dict, key: str, value):
        await self._send(
            "execute", "execute", [f"/sec/networkaudio/{resource}", payload], key, value
        )

    async def _send(self, capability, command, arguments, key=None, value=None):
        """Send one command; record the assumed state only after acceptance."""
        async with self._lock:
            if not self.available:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="smartthings_unavailable"
                )
            await self.adapter.command(capability, command, arguments)
            if key is not None:
                if key == "sound_mode":
                    self.sound_mode_commanded = time.monotonic()
                self.states[key] = value
                self.notify()
        if key == "sound_mode" and self.local is not None:
            self.entry.async_create_background_task(
                self.hass, self.local.async_request_refresh(), f"{DOMAIN} local refresh"
            )
