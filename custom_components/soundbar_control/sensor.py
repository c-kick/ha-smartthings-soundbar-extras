"""Last source reported through the existing SmartThings event stream."""

from homeassistant.components.sensor import SensorEntity

from .const import SOURCE_CAPABILITY
from .entity import SoundbarEntity


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    if runtime.adapter.has_capability(SOURCE_CAPABILITY):
        async_add_entities([SourceSensor(runtime, "input_source")])


class SourceSensor(SoundbarEntity, SensorEntity):
    @property
    def native_value(self):
        return self.runtime.source
