"""Polling coordinator for the Nobreak (NUT) integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_UPS, DOMAIN, NUT_FAKE_SERIAL, SCAN_INTERVAL
from .nut import NutClient, NutError
from .tracker import Tracker, real_power

_LOGGER = logging.getLogger(__name__)

type NobreakConfigEntry = ConfigEntry[NobreakCoordinator]


def unique_id_from_status(status: dict[str, str]) -> str | None:
    """Same id as homeassistant.components.nut, so both share one device."""
    serial = status.get("device.serial") or status.get("ups.serial")
    if not serial or serial.lower() in NUT_FAKE_SERIAL or serial.count("0") == len(serial.strip()):
        return None
    manufacturer = (
        status.get("device.mfr")
        or status.get("ups.mfr")
        or status.get("ups.vendorid")
        or status.get("driver.version.data")
    )
    model = status.get("device.model") or status.get("ups.model") or status.get("ups.productid")
    return "_".join(p for p in (manufacturer, model, serial) if p)


def read_usb_firmware(vendor: str | None, product: str | None) -> str | None:
    """Firmware string straight from the USB descriptors (blocking).

    APC HID units put the firmware in string descriptor 6 (the value of the
    APC_UPS_FirmwareRevision usage), which usbhid-ups never reads. A control
    transfer on endpoint 0 needs no interface claim, so the NUT driver is not
    disturbed. Only works when Home Assistant runs on the host the UPS is
    plugged into.
    """
    # ponytail: APC (051d) only; other vendors keep NUT's ups.firmware if any
    if vendor != "051d" or not product:
        return None
    try:
        import usb.core
        import usb.util

        dev = usb.core.find(idVendor=0x051D, idProduct=int(product, 16))
        if dev is None:
            return None
        return usb.util.get_string(dev, 6) or None
    except Exception as err:  # noqa: BLE001 - optional nicety, never fatal
        _LOGGER.debug("Cannot read USB firmware string: %s", err)
        return None


class NobreakCoordinator(DataUpdateCoordinator[dict[str, str]]):
    """Polls upsd and keeps the derived history."""

    config_entry: NobreakConfigEntry

    def __init__(self, hass: HomeAssistant, entry: NobreakConfigEntry, client: NutClient) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL
        )
        self.client = client
        self.ups: str = entry.data[CONF_UPS]
        self.writable: set[str] = set()
        self.commands: set[str] = set()
        self.firmware: str | None = None
        self.tracker = Tracker()
        self._store: Store[dict] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")

    async def _async_setup(self) -> None:
        try:
            status, self.writable, self.commands = await self.client.snapshot(self.ups)
        except NutError as err:
            raise UpdateFailed(f"upsd: {err}") from err
        if stored := await self._store.async_load():
            self.tracker = Tracker.from_dict(stored)
        self.firmware = status.get("ups.firmware") or await self.hass.async_add_executor_job(
            read_usb_firmware, status.get("ups.vendorid"), status.get("ups.productid")
        )

    async def _async_update_data(self) -> dict[str, str]:
        try:
            data = await self.client.list_vars(self.ups)
        except NutError as err:
            raise UpdateFailed(f"upsd: {err}") from err
        self.tracker.update(
            dt_util.utcnow(),
            set(data.get("ups.status", "").split()),
            real_power(data),
            data.get("ups.test.result"),
        )
        self._store.async_delay_save(self.tracker.to_dict, 60)
        return data

    async def async_save(self) -> None:
        await self._store.async_save(self.tracker.to_dict())

    async def async_set_var(self, name: str, value: str) -> None:
        try:
            await self.client.set_var(self.ups, name, value)
        except NutError as err:
            raise HomeAssistantError(f"upsd refused {name}={value}: {err}") from err
        await self.async_refresh()

    async def async_command(self, command: str) -> None:
        if command.startswith("test.battery.start"):
            self.tracker.expect_test(dt_util.utcnow(), self.data.get("ups.test.result"))
        try:
            await self.client.run_command(self.ups, command)
        except NutError as err:
            raise HomeAssistantError(f"upsd refused {command}: {err}") from err
        await self.async_refresh()
