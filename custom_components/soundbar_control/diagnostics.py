"""Allowlisted diagnostics: never return parent config or raw cloud payloads."""


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = entry.runtime_data
    return {
        "model": entry.data.get("model"),
        "settings": entry.data["settings"],
        "parent_loaded": runtime.adapter.device is not None,
        "available": runtime.available,
        "capabilities": runtime.adapter.capabilities,
        "assumed_states": dict(runtime.states),
    }
