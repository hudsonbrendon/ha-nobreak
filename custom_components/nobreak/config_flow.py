"""Config flow for the Nobreak (NUT) integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME

from .const import CONF_UPS, DEFAULT_HOST, DEFAULT_PORT, DOMAIN
from .coordinator import unique_id_from_status
from .nut import NutClient, NutError


class NobreakConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = NutClient(user_input[CONF_HOST], user_input[CONF_PORT])
            ups = user_input.get(CONF_UPS) or ""
            try:
                upses = await client.list_ups()
                if not ups and len(upses) == 1:
                    ups = next(iter(upses))
                if ups not in upses:
                    errors[CONF_UPS] = "ups_not_found"
                else:
                    status = await client.list_vars(ups)
            except NutError:
                errors["base"] = "cannot_connect"
            if not errors:
                host = user_input[CONF_HOST]
                await self.async_set_unique_id(unique_id_from_status(status) or f"{host}_{ups}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=status.get("device.model") or status.get("ups.model") or ups,
                    data={**user_input, CONF_UPS: ups},
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_USERNAME): str,
                vol.Optional(CONF_PASSWORD): str,
                vol.Optional(CONF_UPS): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )
