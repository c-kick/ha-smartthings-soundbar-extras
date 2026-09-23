"""Assumed sound mode, restored without sending a startup command."""

from homeassistant.components.select import SelectEntity

from .entity import RestoredAssumedEntity
from .profiles import SOUND_MODES


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.runtime_data.enabled("sound_mode"):
        async_add_entities([SoundModeSelect(entry.runtime_data, "sound_mode")])


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
