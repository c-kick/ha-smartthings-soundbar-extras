"""Use real HA OAuth expiration/refresh, mock only the network boundary."""

import time
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session

from custom_components.soundbar_control.smartthings import SmartThingsAdapter

from .conftest import DEVICE


@pytest.fixture
def http():
    response = Mock()
    response.json = AsyncMock(return_value={"results": [{"status": "COMPLETED"}]})
    context = AsyncMock()
    context.__aenter__.return_value = response
    session = Mock()
    session.post.return_value = context
    with patch(
        "custom_components.soundbar_control.smartthings.async_get_clientsession",
        return_value=session,
    ):
        yield session, response


async def test_expired_token_refreshes_once_and_persists(hass, parent, http):
    hass.config_entries.async_update_entry(
        parent,
        data={
            "token": {
                "access_token": "expired",
                "expires_at": 0,
            }
        },
    )
    implementation = Mock()
    implementation.async_refresh_token = AsyncMock(
        return_value={
            "access_token": "fresh",
            "expires_at": time.time() + 3600,
        }
    )
    oauth = OAuth2Session(hass, parent, implementation)

    async def refresh():
        await oauth.async_ensure_token_valid()
        return oauth.token["access_token"]

    parent.runtime_data.client.refresh_token_function = refresh
    adapter = SmartThingsAdapter(hass, parent.entry_id, DEVICE)
    await adapter.command("execute", "execute", [])
    await adapter.command("execute", "execute", [])
    implementation.async_refresh_token.assert_awaited_once()
    assert parent.data["token"]["access_token"] == "fresh"
    assert http[0].post.call_args.kwargs["headers"]["Authorization"] == "Bearer fresh"


@pytest.mark.parametrize(
    "result",
    [
        {},
        [],
        {"results": []},
        {"results": [None]},
        {"results": [{"status": "FAILED"}]},
        {"results": [{"status": "ACCEPTED"}]},
    ],
)
async def test_reject_unknown_response(hass, parent, http, result):
    http[1].json.return_value = result
    with pytest.raises(HomeAssistantError):
        await SmartThingsAdapter(hass, parent.entry_id, DEVICE).command("execute", "execute", [])
    assert http[0].post.call_count == 1


async def test_http_error_is_not_retried(hass, parent, http):
    http[1].raise_for_status.side_effect = aiohttp.ClientError("HTTP 401")
    with pytest.raises(HomeAssistantError):
        await SmartThingsAdapter(hass, parent.entry_id, DEVICE).command("execute", "execute", [])
    assert http[0].post.call_count == 1


async def test_refresh_error_sends_nothing(hass, parent, http):
    parent.runtime_data.client.refresh_token_function = AsyncMock(
        side_effect=HomeAssistantError("refresh")
    )
    with pytest.raises(HomeAssistantError):
        await SmartThingsAdapter(hass, parent.entry_id, DEVICE).command("execute", "execute", [])
    http[0].post.assert_not_called()


async def test_rejected_reply_is_logged(hass, parent, http, caplog):
    http[1].json.return_value = {"results": [{"id": "x", "status": "FAILED"}]}
    with pytest.raises(HomeAssistantError):
        await SmartThingsAdapter(hass, parent.entry_id, DEVICE).command(
            "execute", "execute", []
        )
    assert "execute.execute" in caplog.text
    assert "FAILED" in caplog.text
