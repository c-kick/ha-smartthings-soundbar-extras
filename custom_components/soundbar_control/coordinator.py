"""Poll the local API. Only local entities and the sound-mode mirror depend on this."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_HOST, CONF_POLL_OFF, CONF_POLL_ON, DOMAIN, ISSUE_CERT, ISSUE_UNREACHABLE
from .local_api import LocalApiCertificateChanged, LocalApiException, LocalStatus

_LOGGER = logging.getLogger(__name__)
UNREACHABLE_AFTER = 1800.0


def issue_id(kind: str, entry_id: str) -> str:
    return f"{kind}_{entry_id}"


def delete_local_issues(hass, entry_id: str) -> None:
    for kind in (ISSUE_CERT, ISSUE_UNREACHABLE):
        ir.async_delete_issue(hass, DOMAIN, issue_id(kind, entry_id))


class LocalCoordinator(DataUpdateCoordinator[LocalStatus]):
    """Interval follows the soundbar's own power readback."""

    def __init__(self, hass, entry, runtime, client):
        self._poll_on = timedelta(seconds=entry.options[CONF_POLL_ON])
        self._poll_off = timedelta(seconds=entry.options[CONF_POLL_OFF])
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} local",
            update_interval=self._poll_on,
        )
        self.runtime = runtime
        self.client = client
        self.last_error: str | None = None
        self._failing_since: float | None = None
        self._clock = time.monotonic

    async def _async_update_data(self) -> LocalStatus:
        entry = self.config_entry
        try:
            status = await self.client.status()
        except LocalApiCertificateChanged as err:
            self.last_error = type(err).__name__
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id(ISSUE_CERT, entry.entry_id),
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=ISSUE_CERT,
                translation_placeholders={"name": entry.title},
            )
            # A different problem with its own issue; not part of the unreachable window.
            self._failing_since = None
            self.update_interval = self._poll_off
            raise UpdateFailed("certificate changed") from err
        except LocalApiException as err:
            self.last_error = type(err).__name__
            self._track_failure()
            self.update_interval = self._poll_off
            raise UpdateFailed(type(err).__name__) from err
        self.last_error = None
        self._failing_since = None
        delete_local_issues(self.hass, entry.entry_id)
        self.update_interval = self._poll_off if status.power is False else self._poll_on
        return status

    def _track_failure(self) -> None:
        # The window counts only failures while SmartThings says the soundbar is
        # online: then a silent local API means a wrong address or IP control switched
        # off, not a soundbar that's unplugged.
        if not self.runtime.online:
            self._failing_since = None
            return
        now = self._clock()
        if self._failing_since is None:
            self._failing_since = now
        if now - self._failing_since >= UNREACHABLE_AFTER:
            entry = self.config_entry
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id(ISSUE_UNREACHABLE, entry.entry_id),
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_UNREACHABLE,
                translation_placeholders={
                    "name": entry.title,
                    "host": entry.options[CONF_HOST],
                },
            )
