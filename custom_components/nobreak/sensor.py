"""Sensors: real power/energy and the history upsd does not keep."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import NobreakConfigEntry, NobreakCoordinator
from .entity import NobreakEntity
from .tracker import real_power


def battery_date(data: dict[str, str]) -> date | None:
    """battery.mfr.date as a date; unprogrammed units report garbage like 2107/15/31."""
    try:
        return datetime.strptime(data["battery.mfr.date"], "%Y/%m/%d").date()
    except (KeyError, ValueError):
        return None


def _battery_age(c: NobreakCoordinator) -> int | None:
    if (installed := battery_date(c.data)) is None:
        return None
    return (dt_util.now().date() - installed).days


@dataclass(frozen=True, kw_only=True)
class NobreakSensorDescription(SensorEntityDescription):
    value_fn: Callable[[NobreakCoordinator], Any]
    attrs_fn: Callable[[NobreakCoordinator], dict[str, Any]] | None = None
    exists_fn: Callable[[NobreakCoordinator], bool] = lambda c: True


SENSORS = (
    NobreakSensorDescription(
        key="potencia_de_saida",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda c: real_power(c.data),
        exists_fn=lambda c: real_power(c.data) is not None,
    ),
    NobreakSensorDescription(
        key="energia_de_saida",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda c: round(c.tracker.energy_kwh, 4),
        exists_fn=lambda c: real_power(c.data) is not None,
    ),
    NobreakSensorDescription(
        key="quedas_de_energia",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.tracker.outages,
    ),
    NobreakSensorDescription(
        key="ultima_queda",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: c.tracker.last_outage,
    ),
    NobreakSensorDescription(
        key="duracao_da_ultima_queda",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda c: c.tracker.outage_duration(dt_util.utcnow()),
    ),
    NobreakSensorDescription(
        key="tempo_na_bateria",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=1,
        value_fn=lambda c: round(c.tracker.battery_seconds),
    ),
    NobreakSensorDescription(
        key="ultimo_autoteste",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: c.tracker.last_test,
        attrs_fn=lambda c: {"resultado": c.tracker.last_test_result},
    ),
    NobreakSensorDescription(
        key="idade_da_bateria",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=_battery_age,
        exists_fn=lambda c: "battery.mfr.date" in c.data,
    ),
    NobreakSensorDescription(
        key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.firmware,
        exists_fn=lambda c: c.firmware is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: NobreakConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    c = entry.runtime_data
    async_add_entities(NobreakSensor(c, d) for d in SENSORS if d.exists_fn(c))


class NobreakSensor(NobreakEntity, SensorEntity):
    entity_description: NobreakSensorDescription

    def __init__(self, coordinator: NobreakCoordinator, description: NobreakSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator)
