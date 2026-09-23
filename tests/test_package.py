"""Validate distributable metadata and translation parity."""

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "soundbar_control"


def test_translations_match_and_contain_all_entities():
    strings = json.loads((COMPONENT / "strings.json").read_text())
    assert json.loads((COMPONENT / "translations" / "en.json").read_text()) == strings
    assert set(strings["entity"]["switch"]) == {
        "nightmode",
        "voiceamplifier",
        "bassboost",
        "power_local",
        "mute_local",
    }


def test_manifest_and_hacs():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert manifest["dependencies"] == ["smartthings"]
    assert manifest["config_flow"]
    assert manifest["codeowners"]
    assert json.loads((ROOT / "hacs.json").read_text())["homeassistant"] == "2026.9.0"
