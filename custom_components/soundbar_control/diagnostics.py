"""Allowlisted diagnostics: never return parent config, raw cloud payloads, or addresses."""

from .const import CONF_CERT, CONF_MEDIA_PLAYER, CONF_POLL_OFF, CONF_POLL_ON


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = entry.runtime_data
    local = runtime.local
    local_section = {"enabled": local is not None}
    if local is not None:
        data = local.data
        local_section |= {
            "cert_pinned": bool(entry.options.get(CONF_CERT)),
            "poll_on": entry.options.get(CONF_POLL_ON),
            "poll_off": entry.options.get(CONF_POLL_OFF),
            "media_player": entry.options.get(CONF_MEDIA_PLAYER, True),
            "last_update_success": local.last_update_success,
            "last_error": local.last_error,
            "status": None
            if data is None
            else {
                "power": data.power,
                "input": data.input,
                "sound_mode": data.sound_mode,
                "volume": data.volume,
                "muted": data.muted,
                "codec": data.codec,
                "failed": sorted(data.failed),
            },
        }
    return {
        "model": entry.data.get("model"),
        "settings": entry.data["settings"],
        "parent_loaded": runtime.adapter.device is not None,
        "available": runtime.available,
        "capabilities": runtime.adapter.capabilities,
        "assumed_states": dict(runtime.states),
        "local": local_section,
    }
