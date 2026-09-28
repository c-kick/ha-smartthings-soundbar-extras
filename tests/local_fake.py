"""A TLS fake of Samsung IP Control, and an in-memory stand-in for the client."""

import asyncio
import datetime
import hashlib
import json
import ssl
import time
from dataclasses import replace

from aiohttp import web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from custom_components.soundbar_control.local_api import LocalStatus

# What the real soundbar sends for a bad token, an unknown method and a rejected call.
GENERIC_ERROR = {"code": -32700, "message": "Parse error"}


def make_certificate(directory, common_name="Samsung IP Control G2"):
    """Return (cert_path, key_path, 'AA:BB:…' SHA-256 of the DER certificate)."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_path = directory / f"{common_name.replace(' ', '_')}.pem"
    key_path = directory / f"{common_name.replace(' ', '_')}.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    digest = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).digest()
    return cert_path, key_path, ":".join(f"{b:02X}" for b in digest)


class FakeSoundbar:
    """Serves the subset of Samsung IP Control the integration uses."""

    SOUND_MODES = ("STANDARD", "SURROUND", "GAME", "ADAPTIVE")

    def __init__(self, directory):
        self.cert, self.key, self.sha256 = make_certificate(directory)
        self.state = {
            "power": "powerOn",
            "inputSource": "E_ARC",
            "soundMode": "ADAPTIVE",
            "volume": "10",
            "mute": False,
            "codec": "DTS",
            "identifier": "22_AV_HW-Q930D",
        }
        self.failing: set[str] = set()  # methods that answer GENERIC_ERROR
        self.refuse: set[str] = set()  # write methods that answer {"success": false}
        self.raw: dict[str, object] = {}  # method -> exact JSON body to send
        self.tokens: set[str] = set()
        self.calls: list[tuple[str, dict]] = []
        self.port = 0
        self._runner = None

    async def start(self) -> int:
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(self.cert, self.key)
        app = web.Application()
        app.router.add_post("/", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0, ssl_context=context)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self):
        await self._runner.cleanup()

    def methods(self) -> list[str]:
        return [method for method, _ in self.calls]

    async def _handle(self, request):
        if request.headers.get("Accept") != "application/json":
            return web.Response(status=400)
        body = json.loads(await request.text())
        method, params = body["method"], body.get("params", {})
        self.calls.append((method, params))
        if method in self.raw:
            return web.json_response(self.raw[method])
        if method == "createAccessToken":
            token = f"token-{len(self.tokens)}"
            self.tokens.add(token)
            return self._result({"AccessToken": token})
        if params.get("AccessToken") not in self.tokens or method in self.failing:
            return web.json_response(GENERIC_ERROR)
        return self._dispatch(method, params)

    def _result(self, result):
        return web.json_response({"jsonrpc": "2.0", "id": "1", "result": result})

    def _dispatch(self, method, params):
        state = self.state
        if method in self.refuse and len(params) > 1:  # a write: value plus AccessToken
            return self._result({"success": False})
        reads = {
            "getIdentifier": ("identifier", "identifier"),
            "getVolume": ("volume", "volume"),
            "getMute": ("mute", "mute"),
            "getCodec": ("codec", "codec"),
        }
        if method in reads:
            key, name = reads[method]
            return self._result({name: state[key]})
        if method == "powerControl":
            if "power" in params:
                state["power"] = params["power"]
                return self._result({"success": True})
            return self._result({"power": state["power"]})
        if method == "inputSelectControl":
            if "inputSource" in params:
                state["inputSource"] = params["inputSource"]
                return self._result({"success": True})
            return self._result({"inputSource": state["inputSource"]})
        if method == "soundModeControl":
            if "soundMode" in params:
                if params["soundMode"] not in self.SOUND_MODES:
                    return web.json_response(GENERIC_ERROR)
                state["soundMode"] = params["soundMode"]
                return self._result({"success": True})
            return self._result({"soundMode": state["soundMode"]})
        if method == "volumeControl":
            state["volume"] = str(params["volume"])
            return self._result({"success": True})
        if method == "muteControl":
            state["mute"] = params["mute"]
            return self._result({"success": True})
        return web.json_response(GENERIC_ERROR)


def status(**changes) -> LocalStatus:
    """A healthy status; pass fields to override."""
    base = LocalStatus(
        power=True,
        input="E_ARC",
        sound_mode="ADAPTIVE",
        volume=10,
        muted=False,
        codec="DTS",
        failed=frozenset(),
        read_started=time.monotonic(),
    )
    return replace(base, **changes)


class FakeLocalClient:
    """Same public interface as LocalSoundbarClient, no network."""

    def __init__(self, session=None, host="192.0.2.10", cert_sha256="AA", port=1516):
        self.host = host
        self.value = status()
        self.error: Exception | None = None
        self.gate: asyncio.Event | None = None  # when set, status() waits for it
        self.entered = asyncio.Event()  # set as soon as status() starts
        self.writes: list[tuple[str, object]] = []
        self.write_error: Exception | None = None

    async def identify(self) -> str:
        return "22_AV_HW-Q930D"

    async def status(self) -> LocalStatus:
        started = time.monotonic()
        self.entered.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error
        return replace(self.value, read_started=started)

    async def _write(self, name, value):
        await asyncio.sleep(0)  # a network round-trip lets other calls run meanwhile
        if self.write_error is not None:
            raise self.write_error
        self.writes.append((name, value))
        # Like the real soundbar, the next read reports what was written.
        self.value = replace(self.value, **{name: value})

    async def set_power(self, on):
        await self._write("power", on)

    async def set_input(self, source):
        await self._write("input", source)

    async def set_sound_mode(self, mode):
        await self._write("sound_mode", mode)

    async def set_volume(self, level):
        await self._write("volume", level)

    async def set_mute(self, muted):
        await self._write("muted", muted)
