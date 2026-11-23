"""Actions: run an allow-listed command or set a writable upsd variable."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .controls import SAFE_COMMANDS
from .coordinator import NobreakCoordinator

ATTR_ENTRY = "config_entry_id"

COMMAND_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_ENTRY): cv.string, vol.Required("comando"): vol.In(SAFE_COMMANDS)}
)
VARIABLE_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_ENTRY): cv.string, vol.Required("variavel"): cv.string, vol.Required("valor"): cv.string}
)


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> NobreakCoordinator:
    entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
    if entry_id := call.data.get(ATTR_ENTRY):
        entries = [e for e in entries if e.entry_id == entry_id]
    if len(entries) != 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="escolha_o_nobreak"
        )
    return entries[0].runtime_data


async def _command(call: ServiceCall) -> None:
    coordinator = _coordinator(call.hass, call)
    command = call.data["comando"]
    if command not in coordinator.commands:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="comando_indisponivel", translation_placeholders={"comando": command}
        )
    await coordinator.async_command(command)


async def _set_variable(call: ServiceCall) -> None:
    coordinator = _coordinator(call.hass, call)
    name = call.data["variavel"]
    # driver.* (debug, allow_killpower) stay out of reach of automations
    if name not in coordinator.writable or name.startswith("driver."):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="variavel_nao_gravavel",
            translation_placeholders={"variavel": name, "gravaveis": ", ".join(sorted(v for v in coordinator.writable if not v.startswith("driver.")))},
        )
    await coordinator.async_set_var(name, call.data["valor"])


def async_setup_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "comando", _command, schema=COMMAND_SCHEMA)
    hass.services.async_register(DOMAIN, "definir_variavel", _set_variable, schema=VARIABLE_SCHEMA)
