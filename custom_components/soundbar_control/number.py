"""Individual assumed speaker levels; unknown is not silently initialized to zero."""

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import UnitOfSoundPressure

from .entity import SoundbarEntity
from .profiles import LEVELS, MAX_LEVEL, MIN_LEVEL, valid_level


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    async_add_entities(SpeakerLevelNumber(runtime, key) for key in LEVELS if runtime.enabled(key))


class SpeakerLevelNumber(SoundbarEntity, RestoreNumber):
    _attr_assumed_state = True
    _attr_native_min_value = MIN_LEVEL
    _attr_native_max_value = MAX_LEVEL
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfSoundPressure.DECIBEL
    _attr_mode = NumberMode.SLIDER

    @property
    def native_value(self):
        return self.runtime.states.get(self.key)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self.key not in self.runtime.states:
            restored = await self.async_get_last_number_data()
            if restored and valid_level(restored.native_value):
                self.runtime.states[self.key] = int(restored.native_value)

    async def async_set_native_value(self, value: float):
        await self.runtime.set_level(self.key, value)
