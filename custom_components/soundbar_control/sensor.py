"""Last source reported through the existing SmartThings event stream."""

from homeassistant.components.sensor import SensorEntity

from .const import SOURCE_CAPABILITY
from .entity import SoundbarEntity
from .local_entity import LocalEntity


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    if runtime.adapter.has_capability(SOURCE_CAPABILITY):
        async_add_entities([SourceSensor(runtime, "input_source")])
    if runtime.local is not None:
        async_add_entities([LocalCodecSensor(runtime, "audio_codec")])


class SourceSensor(SoundbarEntity, SensorEntity):
    @property
    def native_value(self):
        return self.runtime.source


class LocalCodecSensor(LocalEntity, SensorEntity):
    """Raw codec string exactly as the soundbar reports it."""

    field = "codec"

    @property
    def native_value(self):
        return self.value
