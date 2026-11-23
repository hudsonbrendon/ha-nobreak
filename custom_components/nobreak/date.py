"""Battery date, stored in the UPS itself (battery.mfr.date)."""

from __future__ import annotations

from datetime import date

from homeassistant.components.date import DateEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .controls import BATTERY_DATE_VAR
from .coordinator import NobreakConfigEntry
from .entity import NobreakEntity
from .sensor import battery_date


async def async_setup_entry(
    hass: HomeAssistant, entry: NobreakConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    c = entry.runtime_data
    if BATTERY_DATE_VAR in c.writable:
        async_add_entities([NobreakBatteryDate(c, "data_da_bateria")])


class NobreakBatteryDate(NobreakEntity, DateEntity):
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def native_value(self) -> date | None:
        return battery_date(self.coordinator.data)

    async def async_set_value(self, value: date) -> None:
        await self.coordinator.async_set_var(BATTERY_DATE_VAR, value.strftime("%Y/%m/%d"))
