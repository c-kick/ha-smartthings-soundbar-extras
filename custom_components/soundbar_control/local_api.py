"""Samsung IP Control: local JSON-RPC over HTTPS on port 1516.

Transport only. It depends on nothing from Home Assistant except the aiohttp session
passed in, so it can be tested against a local TLS server.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import ssl
import time
from dataclasses import dataclass

import aiohttp

LOCAL_PORT = 1516
TIMEOUT = 10
MAX_TEXT = 64
# The soundbar reports a bad token with the same generic error as any rejected call.
# A token that worked this recently is trusted, so an error is about the call itself.
TOKEN_TRUST_SECONDS = 60
KNOWN_INPUTS = ("HDMI_IN1", "HDMI_IN2", "E_ARC", "ARC", "D_IN", "BT", "WIFI_IDLE")
KNOWN_SOUND_MODES = (
    "STANDARD",
    "SURROUND",
    "GAME",
    "MOVIE",
    "MUSIC",
    "CLEARVOICE",
    "DTS_VIRTUAL_X",
    "ADAPTIVE",
)
# Power first: a successful first read proves the token for the rest of the poll.
FIELDS = ("power", "input", "sound_mode", "volume", "muted", "codec")
_SAFE_TEXT = re.compile(rf"[A-Za-z0-9_ .-]{{1,{MAX_TEXT}}}")


class LocalApiException(Exception):
    """Base for every local API failure."""


class LocalApiUnreachable(LocalApiException):
    """Connection failed or timed out. Affects every field."""


class LocalApiRefused(LocalApiUnreachable):
    """Nothing listens on the port: IP control is probably disabled."""


class LocalApiCertificateChanged(LocalApiException):
    """The soundbar presented a certificate other than the pinned one."""


class LocalApiError(LocalApiException):
    """The soundbar answered, but rejected the call or sent something unexpected."""


class LocalApiTokenRejected(LocalApiError):
    """The soundbar refused to issue an access token: IP control is probably disabled."""


@dataclass(frozen=True)
class LocalStatus:
    power: bool | None
    input: str | None
    sound_mode: str | None
    volume: int | None
    muted: bool | None
    codec: str | None
    failed: frozenset[str]
    read_started: float


def valid_value(value: object) -> bool:
    """A soundbar string that is safe to show, store and send back."""
    return isinstance(value, str) and _SAFE_TEXT.fullmatch(value) is not None


def _format_fingerprint(digest: bytes) -> str:
    return ":".join(f"{byte:02X}" for byte in digest)


def _get_pem(host: str, port: int) -> str:
    return ssl.get_server_certificate((host, port), timeout=TIMEOUT)


async def fetch_certificate_sha256(host: str, port: int = LOCAL_PORT) -> str:
    """SHA-256 of the certificate the soundbar presents, as 'AA:BB:…'."""
    loop = asyncio.get_running_loop()
    try:
        pem = await loop.run_in_executor(None, _get_pem, host, port)
    except ConnectionRefusedError as err:
        raise LocalApiRefused(str(err)) from err
    except (OSError, ValueError) as err:
        raise LocalApiUnreachable(str(err)) from err
    return _format_fingerprint(hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).digest())


def _text(result: dict, key: str, *, allow_empty: bool = False) -> str:
    value = result.get(key)
    if allow_empty and value == "":
        return value
    if not valid_value(value):
        raise LocalApiError(f"unexpected {key}")
    return value


class LocalSoundbarClient:
    """One soundbar. Calls are serialized; the soundbar is a small embedded server."""

    def __init__(self, session, host: str, cert_sha256: str, port: int = LOCAL_PORT):
        self._session = session
        self.host = host
        self._port = port
        self._fingerprint = aiohttp.Fingerprint(bytes.fromhex(cert_sha256.replace(":", "")))
        self._token: str | None = None
        self._token_ok_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def url(self) -> str:
        # The host can change at runtime (see __init__.py); bracket IPv6 literals.
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"https://{host}:{self._port}/"

    async def _post(self, method: str, params: dict | None = None) -> dict:
        payload = {"jsonrpc": "2.0", "method": method, "id": 1}
        if params:
            payload["params"] = params
        try:
            async with asyncio.timeout(TIMEOUT):
                async with self._session.post(
                    self.url,
                    data=json.dumps(payload, separators=(",", ":")),
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    ssl=self._fingerprint,
                ) as response:
                    if response.status != 200:
                        raise LocalApiError(f"HTTP {response.status}")
                    body = await response.json(content_type=None)
        except aiohttp.ServerFingerprintMismatch as err:
            raise LocalApiCertificateChanged("certificate changed") from err
        except aiohttp.ClientConnectorError as err:
            if isinstance(err.os_error, ConnectionRefusedError):
                raise LocalApiRefused(str(err)) from err
            raise LocalApiUnreachable(str(err)) from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise LocalApiUnreachable(str(err)) from err
        except ValueError as err:
            raise LocalApiError("invalid JSON") from err
        if not isinstance(body, dict):
            raise LocalApiError("unexpected reply")
        if "result" not in body:
            # Errors come back as {"code": -32700, "message": "Parse error"}, not JSON-RPC.
            raise LocalApiError(f"soundbar error {body.get('code')!r}")
        result = body["result"]
        if not isinstance(result, dict):
            raise LocalApiError("unexpected result")
        return result

    async def _new_token(self) -> None:
        try:
            token = (await self._post("createAccessToken")).get("AccessToken")
        except LocalApiError as err:
            raise LocalApiTokenRejected(str(err)) from err
        if not isinstance(token, str) or not 0 < len(token) <= 512:
            raise LocalApiTokenRejected("no access token")
        self._token = token
        self._token_ok_at = 0.0

    async def _call(self, method: str, **params) -> dict:
        async with self._lock:
            fresh = self._token is None
            if fresh:
                await self._new_token()
            try:
                result = await self._post(method, {**params, "AccessToken": self._token})
            except LocalApiError:
                trusted = time.monotonic() - self._token_ok_at < TOKEN_TRUST_SECONDS
                if fresh or trusted:
                    raise
                # Possibly an expired token: renew once and retry. A rejected command is
                # rejected again, which is harmless.
                await self._new_token()
                result = await self._post(method, {**params, "AccessToken": self._token})
            self._token_ok_at = time.monotonic()
            return result

    async def identify(self) -> str:
        return _text(await self._call("getIdentifier"), "identifier")

    async def _read_power(self) -> bool:
        value = _text(await self._call("powerControl"), "power")
        if value not in ("powerOn", "powerOff"):
            raise LocalApiError("unexpected power")
        return value == "powerOn"

    async def _read_input(self) -> str:
        return _text(await self._call("inputSelectControl"), "inputSource")

    async def _read_sound_mode(self) -> str:
        return _text(await self._call("soundModeControl"), "soundMode")

    async def _read_volume(self) -> int:
        raw = (await self._call("getVolume")).get("volume")
        # The soundbar sends the level as a string, e.g. "10".
        if isinstance(raw, bool) or not isinstance(raw, (str, int)):
            raise LocalApiError("unexpected volume")
        try:
            level = int(raw)
        except ValueError as err:
            raise LocalApiError("unexpected volume") from err
        if not 0 <= level <= 100:
            raise LocalApiError("unexpected volume")
        return level

    async def _read_muted(self) -> bool:
        raw = (await self._call("getMute")).get("mute")
        if not isinstance(raw, bool):
            raise LocalApiError("unexpected mute")
        return raw

    async def _read_codec(self) -> str | None:
        return _text(await self._call("getCodec"), "codec", allow_empty=True) or None

    async def status(self) -> LocalStatus:
        """Read every field. A rejected field is marked failed; the others are kept."""
        started = time.monotonic()
        readers = {
            "power": self._read_power,
            "input": self._read_input,
            "sound_mode": self._read_sound_mode,
            "volume": self._read_volume,
            "muted": self._read_muted,
            "codec": self._read_codec,
        }
        values: dict[str, object] = {}
        failed: set[str] = set()
        for name in FIELDS:
            try:
                values[name] = await readers[name]()
            except LocalApiError:
                values[name] = None
                failed.add(name)
        if len(failed) == len(FIELDS):
            raise LocalApiError("no field could be read")
        return LocalStatus(**values, failed=frozenset(failed), read_started=started)

    async def set_power(self, on: bool) -> None:
        await self._call("powerControl", power="powerOn" if on else "powerOff")

    async def set_input(self, source: str) -> None:
        if not valid_value(source):
            raise ValueError(source)
        await self._call("inputSelectControl", inputSource=source)

    async def set_sound_mode(self, mode: str) -> None:
        if not valid_value(mode):
            raise ValueError(mode)
        await self._call("soundModeControl", soundMode=mode)

    async def set_volume(self, level: int) -> None:
        if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 100:
            raise ValueError(level)
        await self._call("volumeControl", volume=level)

    async def set_mute(self, muted: bool) -> None:
        await self._call("muteControl", mute=bool(muted))
