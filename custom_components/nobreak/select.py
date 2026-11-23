"""Input sensitivity select."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .controls import SENSITIVITY_OPTIONS, SENSITIVITY_VAR
from .coordinator import NobreakConfigEntry
from .entity import NobreakEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: NobreakConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    c = entry.runtime_data
    if SENSITIVITY_VAR in c.writable:
        async_add_entities([NobreakSensitivity(c, "sensibilidade")])


class NobreakSensitivity(NobreakEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = SENSITIVITY_OPTIONS

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.data.get(SENSITIVITY_VAR, "").lower()
        return value if value in SENSITIVITY_OPTIONS else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_var(SENSITIVITY_VAR, option)
