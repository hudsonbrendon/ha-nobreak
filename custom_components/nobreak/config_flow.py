"""Config flow for the Nobreak (NUT) integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_PRICE,
    CONF_SHED1,
    CONF_SHED1_DELAY,
    CONF_SHED2,
    CONF_SHED2_CHARGE,
    CONF_SHED_RESTORE,
    CONF_UPS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_SHED1_DELAY,
    DEFAULT_SHED2_CHARGE,
    DOMAIN,
)
from .coordinator import unique_id_from_status
from .nut import NutClient, NutError

SHED_DOMAINS = ["switch", "light", "fan", "media_player", "climate", "input_boolean", "humidifier", "remote"]


def _number(minimum: float, maximum: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX
        )
    )


class NobreakOptionsFlow(OptionsFlowWithReload):
    """Energy price and two-stage load shedding."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        entities = selector.EntitySelector(selector.EntitySelectorConfig(domain=SHED_DOMAINS, multiple=True))
        schema = vol.Schema(
            {
                vol.Optional(CONF_PRICE): _number(0, 20, 0.001, "/kWh"),
                vol.Optional(CONF_SHED1, default=[]): entities,
                vol.Optional(CONF_SHED1_DELAY, default=DEFAULT_SHED1_DELAY): _number(0, 120, 1, "min"),
                vol.Optional(CONF_SHED2, default=[]): entities,
                vol.Optional(CONF_SHED2_CHARGE, default=DEFAULT_SHED2_CHARGE): _number(5, 95, 1, "%"),
                vol.Optional(CONF_SHED_RESTORE, default=True): selector.BooleanSelector(),
            }
        )
        suggested = dict(self.config_entry.options)
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if CONF_PRICE not in suggested and coordinator is not None and coordinator.grid_price is not None:
            suggested[CONF_PRICE] = coordinator.grid_price
        return self.async_show_form(step_id="init", data_schema=self.add_suggested_values_to_schema(schema, suggested))


class NobreakConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> NobreakOptionsFlow:
        return NobreakOptionsFlow()

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
