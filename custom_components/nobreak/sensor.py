"""Sensors: real power/energy and the history upsd does not keep."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import NobreakConfigEntry, NobreakCoordinator, _float, battery_date
from .entity import NobreakEntity
from .tracker import adequate_range, real_power


def _cost(c: NobreakCoordinator, kwh: float) -> float | None:
    return None if c.price is None else round(kwh * c.price, 2)


def _midnight(c: NobreakCoordinator) -> datetime:
    return dt_util.start_of_local_day()


def _month_start(c: NobreakCoordinator) -> datetime:
    return dt_util.start_of_local_day(dt_util.now().date().replace(day=1))


def _health_attrs(c: NobreakCoordinator) -> dict[str, Any]:
    t = c.tracker
    return {
        "taxa_pct_por_min": t.rate,
        "potencia_media_w": t.rate_power,
        "medido_em": t.measured_at.isoformat() if t.measured_at else None,
        "duracao_s": t.measured_seconds,
        "queda_pct": t.measured_drop,
    }


def _band(c: NobreakCoordinator) -> dict[str, Any]:
    band = adequate_range(_float(c.data, "input.voltage.nominal"))
    return {"faixa_adequada": f"{band[0]:g}–{band[1]:g} V" if band else None}


def _battery_age(c: NobreakCoordinator) -> int | None:
    if (installed := battery_date(c.data)) is None:
        return None
    return (dt_util.now().date() - installed).days


@dataclass(frozen=True, kw_only=True)
class NobreakSensorDescription(SensorEntityDescription):
    value_fn: Callable[[NobreakCoordinator], Any]
    attrs_fn: Callable[[NobreakCoordinator], dict[str, Any]] | None = None
    exists_fn: Callable[[NobreakCoordinator], bool] = lambda c: True
    last_reset_fn: Callable[[NobreakCoordinator], datetime | None] | None = None


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
        attrs_fn=lambda c: {"historico": list(reversed(c.tracker.outage_log[-10:]))},
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
        key="saude_da_bateria",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.tracker.health,
        attrs_fn=_health_attrs,
    ),
    NobreakSensorDescription(
        key="autonomia_real",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda c: c.real_runtime(),
        attrs_fn=lambda c: {
            "ate_desligamento_min": c.real_runtime(_float(c.data, "battery.charge.low") or 0)
        },
    ),
    NobreakSensorDescription(
        key="energia_hoje",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda c: round(c.tracker.energy_today, 4),
        exists_fn=lambda c: real_power(c.data) is not None,
        last_reset_fn=_midnight,
    ),
    NobreakSensorDescription(
        key="energia_do_mes",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda c: round(c.tracker.energy_month, 3),
        exists_fn=lambda c: real_power(c.data) is not None,
        last_reset_fn=_month_start,
    ),
    NobreakSensorDescription(
        key="custo_hoje",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda c: _cost(c, c.tracker.energy_today),
        attrs_fn=lambda c: {"tarifa": c.price},
        exists_fn=lambda c: real_power(c.data) is not None,
        last_reset_fn=_midnight,
    ),
    NobreakSensorDescription(
        key="custo_do_mes",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda c: _cost(c, c.tracker.energy_month),
        attrs_fn=lambda c: {"tarifa": c.price},
        exists_fn=lambda c: real_power(c.data) is not None,
        last_reset_fn=_month_start,
    ),
    NobreakSensorDescription(
        key="tensao_minima_hoje",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value_fn=lambda c: c.tracker.v_min,
        attrs_fn=_band,
        exists_fn=lambda c: "input.voltage" in c.data,
    ),
    NobreakSensorDescription(
        key="tensao_maxima_hoje",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value_fn=lambda c: c.tracker.v_max,
        attrs_fn=_band,
        exists_fn=lambda c: "input.voltage" in c.data,
    ),
    NobreakSensorDescription(
        key="tempo_fora_da_faixa_hoje",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda c: round(c.tracker.out_of_range_seconds),
        attrs_fn=_band,
        exists_fn=lambda c: "input.voltage.nominal" in c.data,
    ),
    NobreakSensorDescription(
        key="regulacoes_avr_hoje",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda c: c.tracker.avr_count,
        last_reset_fn=_midnight,
    ),
    NobreakSensorDescription(
        key="quedas_hoje",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda c: c.tracker.outages_day,
        last_reset_fn=_midnight,
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
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.device_class == SensorDeviceClass.MONETARY:
            return self.hass.config.currency
        return self.entity_description.native_unit_of_measurement

    @property
    def last_reset(self) -> datetime | None:
        fn = self.entity_description.last_reset_fn
        return fn(self.coordinator) if fn else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator)
