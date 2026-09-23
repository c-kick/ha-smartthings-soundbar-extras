"""Assumed sound mode, restored without sending a startup command."""

from homeassistant.components.select import SelectEntity

from .entity import RestoredAssumedEntity
from .local_api import KNOWN_INPUTS, KNOWN_SOUND_MODES
from .local_entity import LocalChoiceSelect
from .profiles import SOUND_MODES


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    if runtime.enabled("sound_mode"):
        async_add_entities([SoundModeSelect(runtime, "sound_mode")])
    if runtime.local is not None:
        async_add_entities(
            [LocalInputSelect(runtime, "input"), LocalSoundModeSelect(runtime, "sound_mode")]
        )


class SoundModeSelect(RestoredAssumedEntity, SelectEntity):
    _attr_assumed_state = True
    _attr_options = list(SOUND_MODES)

    @property
    def current_option(self):
        return self.runtime.states.get(self.key)

    def _valid(self, value) -> bool:
        return value in SOUND_MODES

    def _from_state(self, state: str):
        return state

    async def async_select_option(self, option: str):
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
