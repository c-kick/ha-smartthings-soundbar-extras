"""Assumed sound mode, restored without sending a startup command."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.restore_state import ExtraStoredData

from .const import DOMAIN
from .entity import RestoredAssumedEntity
from .local_api import KNOWN_INPUTS, KNOWN_SOUND_MODES
from .local_entity import MAX_OBSERVED, LocalChoiceSelect, restore_observed
from .profiles import SOUND_MODES


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    if runtime.enabled("sound_mode"):
        async_add_entities([SoundModeSelect(runtime, "sound_mode")])
    if runtime.local is not None:
        async_add_entities(
            [LocalInputSelect(runtime, "input"), LocalSoundModeSelect(runtime, "sound_mode")]
        )


# Local sound modes the cloud select can set itself.
LOCAL_TO_CLOUD = {
    "STANDARD": "standard",
    "SURROUND": "surround",
    "GAME": "game",
    "ADAPTIVE": "adaptive",
}


@dataclass
class SoundModeData(ExtraStoredData):
    value: Any
    extra_options: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"assumed_value": self.value, "extra_options": self.extra_options}


class SoundModeSelect(RestoredAssumedEntity, SelectEntity):
    """Cloud control. Shows the local readback when a fresh one confirms it."""

    def __init__(self, runtime, key):
        super().__init__(runtime, key)
        self._extra_options: list[str] = []

    def _confirmed(self) -> str | None:
        """The local mode, if a reading newer than the last cloud command confirms it."""
        local = self.runtime.local
        if local is None or not local.last_update_success or local.data is None:
            return None
        data = local.data
        if "sound_mode" in data.failed or data.sound_mode is None:
            return None
        if data.read_started <= self.runtime.sound_mode_commanded:
            return None
        return data.sound_mode

    @property
    def options(self) -> list[str]:
        return [*SOUND_MODES, *self._extra_options]

    @property
    def current_option(self):
        mode = self._confirmed()
        if mode is None:
            return self.runtime.states.get(self.key)
        if mode in LOCAL_TO_CLOUD:
            return LOCAL_TO_CLOUD[mode]
        return mode if mode in self._extra_options else self.runtime.states.get(self.key)

    @property
    def assumed_state(self) -> bool:
        mode = self._confirmed()
        return mode is None or (mode not in LOCAL_TO_CLOUD and mode not in self._extra_options)

    @property
    def extra_restore_state_data(self) -> SoundModeData:
        return SoundModeData(self.runtime.states.get(self.key), self._extra_options)

    def _valid(self, value) -> bool:
        return value in SOUND_MODES

    def _from_state(self, state: str):
        return state

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if (extra := await self.async_get_last_extra_data()) is not None:
            restored = restore_observed(extra.as_dict().get("extra_options"))
            self._extra_options = [m for m in restored if m not in LOCAL_TO_CLOUD]
        if self.runtime.local is not None:
            self.async_on_remove(self.runtime.local.async_add_listener(self._local_updated))

    @callback
    def _local_updated(self) -> None:
        mode = self._confirmed()
        if mode in LOCAL_TO_CLOUD:
            self.runtime.states[self.key] = LOCAL_TO_CLOUD[mode]
        elif (
            mode is not None
            and mode not in self._extra_options
            and len(self._extra_options) < MAX_OBSERVED
        ):
            self._extra_options.append(mode)
        self.async_write_ha_state()

    async def async_select_option(self, option: str):
        if option not in SOUND_MODES:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="use_local_sound_mode"
            )
        await self.runtime.set_sound_mode(option)


class LocalInputSelect(LocalChoiceSelect):
    field = "input"
    known = KNOWN_INPUTS

    async def _set(self, option: str) -> None:
        await self.coordinator.client.set_input(option)


class LocalSoundModeSelect(LocalChoiceSelect):
    field = "sound_mode"
    known = KNOWN_SOUND_MODES

    async def _set(self, option: str) -> None:
        await self.coordinator.client.set_sound_mode(option)
