"""The local transport against a TLS fake of the real soundbar's behavior."""

import aiohttp
import pytest

from custom_components.soundbar_control.local_api import (
    FIELDS,
    LocalApiCertificateChanged,
    LocalApiError,
    LocalApiRefused,
    LocalApiUnreachable,
    LocalSoundbarClient,
    fetch_certificate_sha256,
    valid_value,
)

from .local_fake import FakeSoundbar, make_certificate


@pytest.fixture
async def bar(tmp_path, socket_enabled):
    fake = FakeSoundbar(tmp_path)
    await fake.start()
    yield fake
    await fake.stop()


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as client_session:
        yield client_session


def client_for(session, bar, sha256=None):
    return LocalSoundbarClient(session, "127.0.0.1", sha256 or bar.sha256, port=bar.port)


async def test_fetch_certificate_matches_server(bar):
    assert await fetch_certificate_sha256("127.0.0.1", bar.port) == bar.sha256


async def test_fetch_certificate_refused(socket_enabled):
    with pytest.raises(LocalApiRefused):
        await fetch_certificate_sha256("127.0.0.1", 1)


async def test_status_reads_every_field(session, bar):
    status = await client_for(session, bar).status()
    assert status.power is True
    assert status.input == "E_ARC"
    assert status.sound_mode == "ADAPTIVE"
    assert status.volume == 10
    assert status.muted is False
    assert status.codec == "DTS"
    assert status.failed == frozenset()
    # One token, then one call per field.
    assert bar.methods() == [
        "createAccessToken",
        "powerControl",
        "inputSelectControl",
        "soundModeControl",
        "getVolume",
        "getMute",
        "getCodec",
    ]


async def test_requests_send_accept_header(session, bar):
    # The fake answers 400 without Accept, exactly like the soundbar.
    assert (await client_for(session, bar).identify()) == "22_AV_HW-Q930D"


async def test_one_failing_field_keeps_the_others(session, bar):
    bar.failing.add("getCodec")
    status = await client_for(session, bar).status()
    assert status.failed == frozenset({"codec"})
    assert status.codec is None
    assert status.volume == 10


async def test_failing_field_does_not_renew_a_working_token(session, bar):
    bar.failing.add("getCodec")
    await client_for(session, bar).status()
    assert bar.methods().count("createAccessToken") == 1


async def test_all_fields_failing_fails_the_poll(session, bar):
    bar.failing.update(
        {
            "powerControl",
            "inputSelectControl",
            "soundModeControl",
            "getVolume",
            "getMute",
            "getCodec",
        }
    )
    with pytest.raises(LocalApiError):
        await client_for(session, bar).status()


async def test_empty_codec_is_none_but_not_failed(session, bar):
    bar.state["codec"] = ""
    status = await client_for(session, bar).status()
    assert status.codec is None
    assert "codec" not in status.failed


async def test_expired_token_is_renewed_once(session, bar, monkeypatch):
    client = client_for(session, bar)
    await client.identify()
    bar.tokens.clear()  # the soundbar forgot every token
    # Make the earlier success older than the trust window.
    monkeypatch.setattr(client, "_token_ok_at", 0.0)
    assert await client.identify() == "22_AV_HW-Q930D"
    assert bar.methods().count("createAccessToken") == 2


async def test_rejected_write_is_not_retried_with_trusted_token(session, bar):
    client = client_for(session, bar)
    await client.identify()
    with pytest.raises(LocalApiError):
        await client.set_sound_mode("MUSIC")  # the fake only accepts four modes
    assert bar.methods().count("soundModeControl") == 1


async def test_wrong_fingerprint_raises_certificate_changed(session, bar, tmp_path):
    _, _, other = make_certificate(tmp_path, "Somebody Else")
    with pytest.raises(LocalApiCertificateChanged):
        await client_for(session, bar, other).status()
    assert bar.calls == []


async def test_unreachable(session, socket_enabled):
    client = LocalSoundbarClient(session, "127.0.0.1", "AA" * 32, port=1)
    with pytest.raises(LocalApiUnreachable):
        await client.status()


@pytest.mark.parametrize(
    "reply",
    [
        {"jsonrpc": "2.0", "result": {"volume": "250"}},
        {"jsonrpc": "2.0", "result": {"volume": True}},
        {"jsonrpc": "2.0", "result": "10"},
        ["not", "an", "object"],
    ],
)
async def test_malformed_volume_is_a_failed_field(session, bar, reply):
    bar.raw["getVolume"] = reply
    status = await client_for(session, bar).status()
    assert "volume" in status.failed


async def test_oversized_text_is_a_failed_field(session, bar):
    bar.state["inputSource"] = "X" * 65
    status = await client_for(session, bar).status()
    assert "input" in status.failed


@pytest.mark.parametrize(
    ("call", "method", "params"),
    [
        (lambda c: c.set_power(False), "powerControl", {"power": "powerOff"}),
        (lambda c: c.set_input("HDMI_IN1"), "inputSelectControl", {"inputSource": "HDMI_IN1"}),
        (lambda c: c.set_sound_mode("GAME"), "soundModeControl", {"soundMode": "GAME"}),
        (lambda c: c.set_volume(25), "volumeControl", {"volume": 25}),
        (lambda c: c.set_mute(True), "muteControl", {"mute": True}),
    ],
)
async def test_write_payloads(session, bar, call, method, params):
    await call(client_for(session, bar))
    sent = [p for m, p in bar.calls if m == method][-1]
    assert {k: v for k, v in sent.items() if k != "AccessToken"} == params


@pytest.mark.parametrize("level", [-1, 101, 5.5, True, "10"])
async def test_invalid_volume_never_sent(session, bar, level):
    with pytest.raises(ValueError):
        await client_for(session, bar).set_volume(level)
    assert "volumeControl" not in bar.methods()


@pytest.mark.parametrize("value", ["", "x" * 65, "HDMI;rm", "a\nb", None, 5])
def test_valid_value_rejects_unsafe_strings(value):
    assert not valid_value(value)


def test_fields_order_is_power_first():
    # Power first: a successful first read proves the token for the rest of the poll.
    assert FIELDS[0] == "power"
