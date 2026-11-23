"""Diagnostics for the Nobreak (NUT) integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import NobreakConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NobreakConfigEntry
) -> dict[str, Any]:
    c = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), {CONF_PASSWORD, CONF_USERNAME}),
        "variables": c.data,
        "writable": sorted(c.writable),
        "commands": sorted(c.commands),
        "firmware": c.firmware,
        "history": c.tracker.to_dict(),
    }
