"""Entity identity and availability shared by the companion platforms."""

from dataclasses import dataclass
from typing import Any

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .const import DOMAIN


class SoundbarEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runtime, key):
        self.runtime = runtime
        self.key = key
        self._attr_unique_id = f"{runtime.entry.data['device_id']}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.entry.data["device_id"])},
            name=runtime.entry.data["name"],
            manufacturer="Samsung",
            model=runtime.entry.data["model"],
        )
        parent_device = dr.async_get(runtime.hass).async_get_device_by_identifier(
            ("smartthings", runtime.entry.data["device_id"]),
            runtime.entry.data["parent_entry_id"],
        )
        if parent_device:
            self._attr_device_info["via_device_id"] = parent_device.id

    @property
    def available(self):
        return self.runtime.available

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.runtime.listeners.add(self.async_write_ha_state)
        self.async_on_remove(lambda: self.runtime.listeners.discard(self.async_write_ha_state))


@dataclass
class AssumedValue(ExtraStoredData):
    value: Any

    def as_dict(self) -> dict[str, Any]:
        return {"assumed_value": self.value}


class RestoredAssumedEntity(SoundbarEntity, RestoreEntity):
    """Persist the assumed value itself, not the state text.

    HA saves the state text at shutdown. If the entity is unavailable at that moment,
    the text is "unavailable" and the value would be lost.
    """

    def _valid(self, value) -> bool:
        raise NotImplementedError

    def _from_state(self, state: str):
        """Read a value saved by versions that only stored the state text."""
        raise NotImplementedError

    @property
    def extra_restore_state_data(self) -> AssumedValue:
        return AssumedValue(self.runtime.states.get(self.key))

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self.key in self.runtime.states:
            return
        extra = await self.async_get_last_extra_data()
        value = extra.as_dict().get("assumed_value") if extra else None
        if value is None and (state := await self.async_get_last_state()):
            value = self._from_state(state.state)
        if value is not None and self._valid(value):
            self.runtime.states[self.key] = value
