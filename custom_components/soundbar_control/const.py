"""Shared identifiers; no account, device or network details belong here."""

from homeassistant.const import Platform

DOMAIN = "soundbar_control"
NAME = "SmartThings Soundbar Extras"
PLATFORMS = [Platform.SWITCH, Platform.BUTTON, Platform.SENSOR, Platform.SELECT, Platform.NUMBER]
SETTINGS = ("nightmode", "voiceamplifier", "bassboost")
SOURCE_CAPABILITY = "samsungvd.audioInputSource"
PREFIX = "x.com.samsung.networkaudio."
