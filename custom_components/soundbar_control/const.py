"""Shared identifiers; no account, device or network details belong here."""

from homeassistant.const import Platform

DOMAIN = "soundbar_control"
NAME = "SmartThings Soundbar Extras"
PLATFORMS = [Platform.SWITCH, Platform.BUTTON, Platform.SENSOR, Platform.SELECT, Platform.NUMBER]
SETTINGS = ("nightmode", "voiceamplifier", "bassboost")
SOURCE_CAPABILITY = "samsungvd.audioInputSource"
PREFIX = "x.com.samsung.networkaudio."

CONF_USE_LOCAL = "use_local_api"
CONF_HOST = "host"
CONF_MAC = "mac"
CONF_CERT = "cert_sha256"
CONF_POLL_ON = "poll_on"
CONF_POLL_OFF = "poll_off"
DEFAULT_POLL_ON = 5
DEFAULT_POLL_OFF = 60
ISSUE_CERT = "certificate_changed"
ISSUE_UNREACHABLE = "local_unreachable"
# SmartThings accepting a sound-mode command doesn't mean the soundbar applied it:
# only a local reading started this long after the command confirms the mode.
SOUND_MODE_SETTLE = 2.0
