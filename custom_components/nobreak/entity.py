"""Base entity for the Nobreak (NUT) integration."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NUT_DOMAIN
from .coordinator import NobreakCoordinator

# ponytail: HA 2026.11 replaced DeviceInfo.via_device (deprecated, gone in
# 2027.8) by via_device_id; drop the fallback once the minimum HA is 2026.11
_VIA_DEVICE_ID = "via_device_id" in getattr(DeviceInfo, "__annotations__", {})


def _nut_device(coordinator: NobreakCoordinator, uid: str) -> dr.DeviceEntry | None:
    """The core NUT device of the same UPS (its entry has the same unique id)."""
    hass = coordinator.hass
    for entry in hass.config_entries.async_entries(NUT_DOMAIN):
        if entry.unique_id == uid:
            return dr.async_get(hass).async_get_device_by_identifier((NUT_DOMAIN, uid), entry.entry_id)
    return None


class NobreakEntity(CoordinatorEntity[NobreakCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: NobreakCoordinator, key: str) -> None:
        super().__init__(coordinator)
        uid = coordinator.config_entry.unique_id
        data = coordinator.data
        self._attr_translation_key = key
        self._attr_unique_id = f"{uid}_{key}"
        # Since HA 2026.11 identifiers are scoped per config entry, so the
        # core NUT device cannot be shared; link to it as "connected via".
        ups = coordinator.ups
        info: dict = {
            "identifiers": {(DOMAIN, uid)},
            "name": "Nobreak" if ups in ("myups", "ups") else f"Nobreak {ups}",
            "manufacturer": data.get("device.mfr") or data.get("ups.mfr"),
            "model": data.get("device.model") or data.get("ups.model"),
            "serial_number": data.get("device.serial") or data.get("ups.serial"),
            "sw_version": coordinator.firmware,
        }
        if not _VIA_DEVICE_ID:
            info["via_device"] = (NUT_DOMAIN, uid)
        elif nut := _nut_device(coordinator, uid):
            info["via_device_id"] = nut.id
        self._attr_device_info = DeviceInfo(**info)

    @property
    def status(self) -> set[str]:
        return set(self.coordinator.data.get("ups.status", "").split())
