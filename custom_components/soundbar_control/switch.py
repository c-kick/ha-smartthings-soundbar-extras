"""Native, restored, assumed-state advanced audio switches."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, STATE_ON

from .const import SETTINGS
from .entity import RestoredAssumedEntity


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    async_add_entities(SoundbarSwitch(runtime, key) for key in SETTINGS if runtime.enabled(key))


class SoundbarSwitch(RestoredAssumedEntity, SwitchEntity):
    _attr_assumed_state = True

    @property
    def is_on(self):
        return self.runtime.states.get(self.key)

    def _valid(self, value) -> bool:
        return isinstance(value, bool)

    def _from_state(self, state: str):
        return {STATE_ON: True, STATE_OFF: False}.get(state)

    async def async_turn_on(self, **kwargs):
        await self.runtime.set(self.key, True)

    async def async_turn_off(self, **kwargs):
        await self.runtime.set(self.key, False)
