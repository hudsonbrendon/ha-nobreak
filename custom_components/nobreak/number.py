"""Writable numeric upsd variables (transfer voltages, delays, limits)."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfElectricPotential, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .controls import NUMBERS, NumberVar
from .coordinator import NobreakConfigEntry, NobreakCoordinator
from .entity import NobreakEntity

_DEVICE_CLASS = {
    UnitOfElectricPotential.VOLT: NumberDeviceClass.VOLTAGE,
    UnitOfTime.SECONDS: NumberDeviceClass.DURATION,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: NobreakConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    c = entry.runtime_data
    async_add_entities(NobreakNumber(c, n) for n in NUMBERS if n.var in c.writable)


class NobreakNumber(NobreakEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: NobreakCoordinator, spec: NumberVar) -> None:
        super().__init__(coordinator, spec.key)
        self._var = spec.var
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_device_class = _DEVICE_CLASS.get(spec.unit)
        self._attr_native_min_value = spec.min
        self._attr_native_max_value = spec.max
        self._attr_native_step = spec.step

    @property
    def native_value(self) -> float | None:
        try:
            return float(self.coordinator.data[self._var])
        except (KeyError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_var(self._var, str(int(value)))
