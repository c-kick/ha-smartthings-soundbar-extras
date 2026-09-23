"""Local API entities: real readback, so never assumed state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .local_api import LocalApiCertificateChanged, LocalApiError, LocalApiException, valid_value

MAX_OBSERVED = 20


class LocalEntity(CoordinatorEntity):
    _attr_has_entity_name = True
    field: str

    def __init__(self, runtime, key: str):
        super().__init__(runtime.local)
        self.runtime = runtime
        device_id = runtime.entry.data["device_id"]
        self._attr_unique_id = f"{device_id}_{key}_local"
        self._attr_translation_key = f"{key}_local"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device_id)})

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return super().available and data is not None and self.field not in data.failed

    @property
    def value(self):
        data = self.coordinator.data
        return getattr(data, self.field) if data is not None else None

    async def write(self, coro) -> None:
        try:
            await coro
        except LocalApiCertificateChanged as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="local_unavailable"
            ) from err
        except LocalApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="local_rejected"
            ) from err
        except LocalApiException as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="local_unavailable"
            ) from err
        await self.coordinator.async_request_refresh()


def restore_observed(raw: Any) -> list[str]:
    """Keep only safe, unique strings from stored data."""
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        if valid_value(item) and item not in result:
            result.append(item)
    return result[:MAX_OBSERVED]


@dataclass
class ObservedOptions(ExtraStoredData):
    observed: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"observed": self.observed}


class LocalChoiceSelect(LocalEntity, SelectEntity, RestoreEntity):
    """Known values plus any the soundbar has reported, remembered across restarts."""

    known: tuple[str, ...]

    def __init__(self, runtime, key: str):
        super().__init__(runtime, key)
        self._observed: list[str] = []

    @property
    def options(self) -> list[str]:
        return [*self.known, *self._observed]

    @property
    def current_option(self) -> str | None:
        value = self.value
        return value if value in self.options else None

    @property
    def extra_restore_state_data(self) -> ObservedOptions:
        return ObservedOptions(self._observed)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (extra := await self.async_get_last_extra_data()) is not None:
            restored = restore_observed(extra.as_dict().get("observed"))
            self._observed = [value for value in restored if value not in self.known]

    @callback
    def _handle_coordinator_update(self) -> None:
        value = self.value if self.available else None
        if (
            valid_value(value)
            and value not in self.known
            and value not in self._observed
            and len(self._observed) < MAX_OBSERVED
        ):
            self._observed.append(value)
        super()._handle_coordinator_update()

    async def _set(self, option: str) -> None:
        raise NotImplementedError

    async def async_select_option(self, option: str) -> None:
        await self.write(self._set(option))
