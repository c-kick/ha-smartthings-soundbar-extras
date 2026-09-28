"""Player (local): the local API as one media player, for a quick-reacting dashboard."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .const import CONF_MEDIA_PLAYER, DOMAIN
from .local_api import KNOWN_INPUTS, KNOWN_SOUND_MODES
from .local_entity import LocalEntity, ObservedValues

KEY = "player"


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    if runtime.local is not None and entry.options.get(CONF_MEDIA_PLAYER, True):
        async_add_entities([LocalMediaPlayer(runtime, KEY)])
        return
    # Switched off: remove the entity instead of leaving a "no longer provided" entry.
    registry = er.async_get(hass)
    unique_id = f"{entry.data['device_id']}_{KEY}_local"
    if entity_id := registry.async_get_entity_id("media_player", DOMAIN, unique_id):
        registry.async_remove(entity_id)


@dataclass
class ReportedValues(ExtraStoredData):
    inputs: list[str]
    sound_modes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"inputs": self.inputs, "sound_modes": self.sound_modes}


class LocalMediaPlayer(LocalEntity, MediaPlayerEntity, RestoreEntity):
    """Available while power can be read; other fields may be missing on their own."""

    field = "power"
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.SELECT_SOUND_MODE
    )

    def __init__(self, runtime, key: str):
        super().__init__(runtime, key)
        self._inputs = ObservedValues(KNOWN_INPUTS)
        self._sound_modes = ObservedValues(KNOWN_SOUND_MODES)

    def _read(self, field: str):
        data = self.coordinator.data
        return getattr(data, field) if data is not None else None

    @property
    def state(self) -> MediaPlayerState | None:
        power = self.value
        if power is None:
            return None
        return MediaPlayerState.ON if power else MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        volume = self._read("volume")
        return None if volume is None else volume / 100

    @property
    def is_volume_muted(self) -> bool | None:
        return self._read("muted")

    @property
    def source(self) -> str | None:
        return self._read("input")

    @property
    def source_list(self) -> list[str]:
        return self._inputs.options

    @property
    def sound_mode(self) -> str | None:
        return self._read("sound_mode")

    @property
    def sound_mode_list(self) -> list[str]:
        return self._sound_modes.options

    @property
    def extra_restore_state_data(self) -> ReportedValues:
        return ReportedValues(self._inputs.extra, self._sound_modes.extra)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (extra := await self.async_get_last_extra_data()) is not None:
            stored = extra.as_dict()
            self._inputs.restore(stored.get("inputs"))
            self._sound_modes.restore(stored.get("sound_modes"))

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.available:
            self._inputs.add(self._read("input"))
            self._sound_modes.add(self._read("sound_mode"))
        super()._handle_coordinator_update()

    async def async_turn_on(self) -> None:
        await self.write(self.coordinator.client.set_power(True), power=True)

    async def async_turn_off(self) -> None:
        await self.write(self.coordinator.client.set_power(False), power=False)

    async def _set_volume(self, level: int) -> None:
        level = max(0, min(100, level))
        await self.write(self.coordinator.client.set_volume(level), volume=level)

    async def async_set_volume_level(self, volume: float) -> None:
        await self._set_volume(round(volume * 100))

    async def _step_volume(self, step: int) -> None:
        # Counts from the last accepted value, so quick steps add up.
        volume = self._read("volume")
        if volume is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="local_unavailable")
        await self._set_volume(volume + step)

    async def async_volume_up(self) -> None:
        await self._step_volume(1)

    async def async_volume_down(self) -> None:
        await self._step_volume(-1)

    async def async_mute_volume(self, mute: bool) -> None:
        await self.write(self.coordinator.client.set_mute(mute), muted=mute)

    async def async_select_source(self, source: str) -> None:
        await self.write(self.coordinator.client.set_input(source), input=source)

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        await self.write(self.coordinator.client.set_sound_mode(sound_mode), sound_mode=sound_mode)
