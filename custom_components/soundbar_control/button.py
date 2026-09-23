"""Source cycling where Samsung only exposes setNextInputSource."""

from homeassistant.components.button import ButtonEntity

from .const import SOURCE_CAPABILITY
from .entity import SoundbarEntity


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    if runtime.adapter.has_capability(SOURCE_CAPABILITY):
        async_add_entities([NextSourceButton(runtime, "next_source")])


class NextSourceButton(SoundbarEntity, ButtonEntity):
    async def async_press(self):
        await self.runtime.next_source()
