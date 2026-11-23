"""Base entity for the Nobreak (NUT) integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NUT_DOMAIN
from .coordinator import NobreakCoordinator


class NobreakEntity(CoordinatorEntity[NobreakCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: NobreakCoordinator, key: str) -> None:
        super().__init__(coordinator)
        uid = coordinator.config_entry.unique_id
        data = coordinator.data
        self._attr_translation_key = key
        self._attr_unique_id = f"{uid}_{key}"
        # Since HA 2026.11 identifiers are scoped per config entry, so the
        # core NUT device cannot be shared; link to it with via_device instead.
        ups = coordinator.ups
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            via_device=(NUT_DOMAIN, uid),
            name="Nobreak" if ups in ("myups", "ups") else f"Nobreak {ups}",
            manufacturer=data.get("device.mfr") or data.get("ups.mfr"),
            model=data.get("device.model") or data.get("ups.model"),
            serial_number=data.get("device.serial") or data.get("ups.serial"),
            sw_version=coordinator.firmware,
        )

    @property
    def status(self) -> set[str]:
        return set(self.coordinator.data.get("ups.status", "").split())
