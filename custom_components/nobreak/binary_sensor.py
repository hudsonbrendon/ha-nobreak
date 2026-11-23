"""Binary sensors from the ups.status flags."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NobreakConfigEntry, NobreakCoordinator
from .entity import NobreakEntity


@dataclass(frozen=True, kw_only=True)
class NobreakBinaryDescription(BinarySensorEntityDescription):
    is_on_fn: Callable[[set[str], dict[str, str]], bool]


def _shutdown_pending(status: set[str], data: dict[str, str]) -> bool:
    try:
        return float(data.get("ups.timer.shutdown", "-1")) >= 0
    except ValueError:
        return False


BINARY_SENSORS = (
    NobreakBinaryDescription(
        key="rede_eletrica",
        device_class=BinarySensorDeviceClass.POWER,
        is_on_fn=lambda s, d: "OL" in s,
    ),
    NobreakBinaryDescription(
        key="bateria_fraca",
        device_class=BinarySensorDeviceClass.BATTERY,
        is_on_fn=lambda s, d: "LB" in s,
    ),
    NobreakBinaryDescription(
        key="carregando",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        is_on_fn=lambda s, d: "CHRG" in s,
    ),
    NobreakBinaryDescription(
        key="substituir_bateria",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda s, d: "RB" in s,
    ),
    NobreakBinaryDescription(
        key="sobrecarga",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda s, d: "OVER" in s,
    ),
    NobreakBinaryDescription(
        key="avr",
        is_on_fn=lambda s, d: bool(s & {"BOOST", "TRIM"}),
    ),
    NobreakBinaryDescription(
        key="desligamento_agendado",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=_shutdown_pending,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: NobreakConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    c = entry.runtime_data
    async_add_entities(NobreakBinarySensor(c, d) for d in BINARY_SENSORS)


class NobreakBinarySensor(NobreakEntity, BinarySensorEntity):
    entity_description: NobreakBinaryDescription

    def __init__(self, coordinator: NobreakCoordinator, description: NobreakBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.is_on_fn(self.status, self.coordinator.data)
