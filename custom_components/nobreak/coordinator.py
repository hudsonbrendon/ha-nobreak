"""Polling coordinator for the Nobreak (NUT) integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_PRICE,
    CONF_SHED1,
    CONF_SHED1_DELAY,
    CONF_SHED2,
    CONF_SHED2_CHARGE,
    CONF_SHED_RESTORE,
    CONF_UPS,
    DEFAULT_SHED1_DELAY,
    DEFAULT_SHED2_CHARGE,
    DOMAIN,
    HEALTH_ISSUE_BELOW,
    NUT_FAKE_SERIAL,
    OLD_BATTERY_DAYS,
    SCAN_INTERVAL,
)
from .nut import NutClient, NutError
from .tracker import Event, Sample, Tracker, real_power

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


def _float(data: dict[str, str], key: str) -> float | None:
    try:
        return float(data[key])
    except (KeyError, ValueError):
        return None


def battery_date(data: dict[str, str]) -> date | None:
    """battery.mfr.date as a date; unprogrammed units report garbage like 2107/15/31."""
    try:
        return datetime.strptime(data["battery.mfr.date"], "%Y/%m/%d").date()
    except (KeyError, ValueError):
        return None


async def load_grid_price(hass: HomeAssistant) -> float | None:
    """Fixed grid price (per kWh) of the Energy dashboard, if one is set."""
    try:
        from homeassistant.components.energy.data import async_get_manager

        manager = await async_get_manager(hass)
    except Exception:  # noqa: BLE001 - energy not set up: just no default price
        return None
    for source in (manager.data or {}).get("energy_sources", []):
        if source.get("type") == "grid" and source.get("number_energy_price") is not None:
            return float(source["number_energy_price"])
    return None


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
        self.events: list[Event] = []
        self.grid_price: float | None = None
        self._store: Store[dict] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")

    @property
    def price(self) -> float | None:
        """R$/kWh: the option, else the fixed grid price of the Energy dashboard."""
        value = self.config_entry.options.get(CONF_PRICE)
        return float(value) if value not in (None, "") else self.grid_price

    def real_runtime(self, floor: float = 0) -> float | None:
        return self.tracker.real_runtime(
            real_power(self.data), _float(self.data, "battery.charge"), floor
        )

    async def _async_setup(self) -> None:
        try:
            status, self.writable, self.commands = await self.client.snapshot(self.ups)
        except NutError as err:
            raise UpdateFailed(f"upsd: {err}") from err
        if stored := await self._store.async_load():
            self.tracker = Tracker.from_dict(stored)
        self.grid_price = await load_grid_price(self.hass)
        self.firmware = status.get("ups.firmware") or await self.hass.async_add_executor_job(
            read_usb_firmware, status.get("ups.vendorid"), status.get("ups.productid")
        )

    async def _async_update_data(self) -> dict[str, str]:
        try:
            data = await self.client.list_vars(self.ups)
        except NutError as err:
            raise UpdateFailed(f"upsd: {err}") from err
        local = dt_util.now()
        sample = Sample(
            now=dt_util.utcnow(),
            day=local.date().isoformat(),
            month=local.strftime("%Y-%m"),
            status=set(data.get("ups.status", "").split()),
            power=real_power(data),
            test_result=data.get("ups.test.result"),
            charge=_float(data, "battery.charge"),
            runtime=_float(data, "battery.runtime"),
            voltage=_float(data, "input.voltage"),
            nominal_voltage=_float(data, "input.voltage.nominal"),
        )
        self.events = self.tracker.update(sample)
        self.events += self._shed(sample)
        self._repairs(data)
        self._store.async_delay_save(self.tracker.to_dict, 60)
        return data

    # ── load shedding ──────────────────────────────────────────────────────
    def _shed(self, s: Sample) -> list[Event]:
        """Turn non-essentials off in two stages while on battery; back on afterwards."""
        tr, opts = self.tracker, self.config_entry.options
        on_battery = "OB" in s.status
        if not on_battery:
            if not (tr.shed_stage1 or tr.shed_stage2):
                return []
            back = list(tr.shed_off) if opts.get(CONF_SHED_RESTORE, True) else []
            tr.shed_stage1 = tr.shed_stage2 = False
            tr.shed_off = []
            if back:
                self._call("turn_on", back)
                return [("economia", {"estagio": 0, "religados": back})]
            return []
        if not tr.shed_enabled or tr.in_test(s.now, s.test_result) or tr.outage_start is None:
            return []
        events: list[Event] = []
        delay = float(opts.get(CONF_SHED1_DELAY, DEFAULT_SHED1_DELAY)) * 60
        if not tr.shed_stage1 and (s.now - tr.outage_start).total_seconds() >= delay:
            tr.shed_stage1 = True
            events += self._shed_stage(1, opts.get(CONF_SHED1, []))
        limit = float(opts.get(CONF_SHED2_CHARGE, DEFAULT_SHED2_CHARGE))
        if not tr.shed_stage2 and s.charge is not None and s.charge <= limit:
            tr.shed_stage2 = True
            events += self._shed_stage(2, opts.get(CONF_SHED2, []))
        return events

    def _shed_stage(self, stage: int, entities: list[str]) -> list[Event]:
        on = [e for e in entities if (st := self.hass.states.get(e)) and st.state not in ("off", "unavailable", "unknown")]
        if not on:
            return []
        self.tracker.shed_off = sorted({*self.tracker.shed_off, *on})
        self._call("turn_off", on)
        return [("economia", {"estagio": stage, "desligados": on})]

    def _call(self, service: str, entities: list[str]) -> None:
        self.hass.async_create_task(
            self.hass.services.async_call("homeassistant", service, {"entity_id": entities}, blocking=False)
        )

    # ── repairs ────────────────────────────────────────────────────────────
    def _repairs(self, data: dict[str, str]) -> None:
        tr = self.tracker
        installed = battery_date(data)
        age = (dt_util.now().date() - installed).days if installed else None
        result = tr.last_test_result or ""
        self._issue(
            "substituir_bateria",
            "RB" in data.get("ups.status", "").split(),
            ir.IssueSeverity.ERROR,
        )
        self._issue(
            "autoteste_reprovado",
            result.startswith(("Done and error", "Done and warning")),
            ir.IssueSeverity.ERROR if "error" in result else ir.IssueSeverity.WARNING,
            {"resultado": result},
        )
        self._issue(
            "bateria_antiga",
            age is not None and age >= OLD_BATTERY_DAYS,
            ir.IssueSeverity.WARNING,
            {"anos": f"{(age or 0) / 365:.1f}", "data": installed.isoformat() if installed else ""},
        )
        self._issue(
            "saude_baixa",
            tr.health is not None and tr.health < HEALTH_ISSUE_BELOW,
            ir.IssueSeverity.WARNING,
            {"saude": f"{tr.health or 0:.0f}"},
        )

    def _issue(self, key: str, active: bool, severity: ir.IssueSeverity, placeholders: dict | None = None) -> None:
        issue_id = f"{key}_{self.config_entry.entry_id}"
        if active:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=severity,
                translation_key=key,
                translation_placeholders=placeholders,
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    async def async_save(self) -> None:
        await self._store.async_save(self.tracker.to_dict())

    async def async_set_var(self, name: str, value: str) -> None:
        try:
            await self.client.set_var(self.ups, name, value)
        except NutError as err:
            raise HomeAssistantError(f"upsd refused {name}={value}: {err}") from err
        # ponytail: the driver writes the HID report and only then re-reads it
        # into upsd; 2 s covers its pollinterval, a read-back loop if ever needed
        await asyncio.sleep(2)
        await self.async_refresh()

    async def async_command(self, command: str) -> None:
        if command.startswith("test.battery.start"):
            self.tracker.expect_test(dt_util.utcnow(), self.data.get("ups.test.result"))
        try:
            await self.client.run_command(self.ups, command)
        except NutError as err:
            raise HomeAssistantError(f"upsd refused {command}: {err}") from err
        await self.async_refresh()
