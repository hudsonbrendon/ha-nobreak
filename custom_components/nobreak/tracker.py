"""History the UPS does not keep: energy, outages, battery health, grid quality.

Pure Python (no Home Assistant imports) so it can be unit tested directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

# A longer gap between two samples (HA stopped, upsd down) is not integrated.
MAX_GAP = timedelta(minutes=5)
# A self-test we started puts the UPS on battery for a few seconds; not an outage.
TEST_GRACE = timedelta(seconds=90)
FINISHED_TEST = ("Done", "Aborted")
QUICK_TEST = timedelta(seconds=30)
TEST_TIMEOUT = timedelta(hours=2)
MAX_LOG = 50
# A discharge only says something about the battery when it is long enough.
MIN_MEASURE_SECONDS = 60
MIN_MEASURE_DROP = 2.0
DATETIME_FIELDS = ("last_outage", "outage_start", "last_test", "measured_at", "dis_start")


def real_power(data: dict[str, str]) -> float | None:
    """Output active power in W: ups.realpower, else load % x nominal W."""
    try:
        if "ups.realpower" in data:
            return round(float(data["ups.realpower"]), 1)
        return round(
            float(data["ups.load"]) * float(data["ups.realpower.nominal"]) / 100, 1
        )
    except (KeyError, ValueError):
        return None


def adequate_range(nominal: float | None) -> tuple[float, float] | None:
    """ANEEL PRODIST "adequate" steady-state band: 0.92-1.05 x nominal (202-231 V @ 220 V)."""
    if not nominal:
        return None
    return round(nominal * 0.92, 1), round(nominal * 1.05, 1)


@dataclass
class Sample:
    """One poll of upsd, already parsed by the coordinator."""

    now: datetime
    day: str  # local date, ISO
    month: str  # local YYYY-MM
    status: set[str]
    power: float | None = None
    test_result: str | None = None
    charge: float | None = None
    runtime: float | None = None  # seconds
    voltage: float | None = None
    nominal_voltage: float | None = None


Event = tuple[str, dict]


@dataclass
class Tracker:
    energy_kwh: float = 0.0
    outages: int = 0
    last_outage: datetime | None = None
    last_outage_seconds: float | None = None
    outage_start: datetime | None = None
    outage_start_charge: float | None = None
    outage_min_charge: float | None = None
    outage_energy0: float | None = None
    outage_log: list[dict] = field(default_factory=list)
    battery_seconds: float = 0.0
    last_test: datetime | None = None
    last_test_result: str | None = None
    # battery health, measured on every discharge (outage or test)
    health: float | None = None
    rate: float | None = None  # % per minute
    rate_power: float | None = None  # mean W during that discharge
    measured_at: datetime | None = None
    measured_seconds: float | None = None
    measured_drop: float | None = None
    dis_start: datetime | None = None
    dis_charge0: float | None = None
    dis_runtime0: float | None = None
    dis_energy0: float | None = None
    dis_min_charge: float | None = None
    # today / this month
    day: str | None = None
    v_min: float | None = None
    v_max: float | None = None
    out_of_range_seconds: float = 0.0
    avr_count: int = 0
    outages_day: int = 0
    energy_day0: float = 0.0
    month: str | None = None
    energy_month0: float = 0.0
    # load shedding (driven by the coordinator)
    shed_enabled: bool = True
    shed_stage1: bool = False
    shed_stage2: bool = False
    shed_off: list[str] = field(default_factory=list)
    _test_started: datetime | None = field(default=None, repr=False)
    _test_baseline: str | None = field(default=None, repr=False)
    _test_progress: bool = field(default=False, repr=False)
    _prev: tuple[datetime, float | None, bool] | None = field(default=None, repr=False)
    _prev_avr: bool = field(default=False, repr=False)
    _seen_result: str | None = field(default=None, repr=False)

    # ── derived values ─────────────────────────────────────────────────────
    @property
    def energy_today(self) -> float:
        return max(0.0, self.energy_kwh - self.energy_day0)

    @property
    def energy_month(self) -> float:
        return max(0.0, self.energy_kwh - self.energy_month0)

    def outage_duration(self, now: datetime) -> float | None:
        if self.outage_start is not None:
            return round((now - self.outage_start).total_seconds())
        return self.last_outage_seconds

    def real_runtime(self, power: float | None, charge: float | None, floor: float = 0) -> float | None:
        """Minutes until `floor` % at `power` W, from the measured discharge rate."""
        if not (self.rate and self.rate_power and power and charge is not None):
            return None
        rate_now = self.rate * power / self.rate_power
        return round(max(0.0, charge - floor) / rate_now, 1) if rate_now > 0 else None

    def expect_test(self, now: datetime, current_result: str | None) -> None:
        """A battery test was just requested: record its result, ignore its OB."""
        self._test_started, self._test_baseline, self._test_progress = now, current_result, False

    def in_test(self, now: datetime, result: str | None) -> bool:
        if result == "In progress":
            return True
        return self._test_started is not None and now - self._test_started < TEST_GRACE

    # ── update ─────────────────────────────────────────────────────────────
    def update(self, s: Sample) -> list[Event]:
        events: list[Event] = []
        now = s.now
        on_battery = "OB" in s.status
        dt = 0.0
        if self._prev is not None:
            then, prev_power, was_on_battery = self._prev
            gap = (now - then).total_seconds()
            if 0 < gap <= MAX_GAP.total_seconds():
                dt = gap
                if prev_power is not None and s.power is not None:
                    self.energy_kwh += (prev_power + s.power) / 2 * dt / 3_600_000
                if was_on_battery and on_battery:
                    self.battery_seconds += dt
        self._prev = (now, s.power, on_battery)

        self._roll_period(s)
        self._grid_quality(s, on_battery, dt)
        events += self._outages(s, on_battery)
        events += self._discharge(s, on_battery)
        events += self._tests(s)
        return events

    def _roll_period(self, s: Sample) -> None:
        if self.day != s.day:
            self.day, self.v_min, self.v_max = s.day, None, None
            self.out_of_range_seconds, self.avr_count, self.outages_day = 0.0, 0, 0
            self.energy_day0 = self.energy_kwh
        if self.month != s.month:
            self.month, self.energy_month0 = s.month, self.energy_kwh

    def _grid_quality(self, s: Sample, on_battery: bool, dt: float) -> None:
        if s.voltage and not on_battery:
            self.v_min = s.voltage if self.v_min is None else min(self.v_min, s.voltage)
            self.v_max = s.voltage if self.v_max is None else max(self.v_max, s.voltage)
            band = adequate_range(s.nominal_voltage)
            if band and dt and not band[0] <= s.voltage <= band[1]:
                self.out_of_range_seconds += dt
        avr = bool(s.status & {"BOOST", "TRIM"})
        if avr and not self._prev_avr:
            self.avr_count += 1
        self._prev_avr = avr

    def _outages(self, s: Sample, on_battery: bool) -> list[Event]:
        now = s.now
        if on_battery and self.outage_start is None and not self.in_test(now, s.test_result):
            self.outages += 1
            self.outages_day += 1
            self.last_outage = self.outage_start = now
            self.outage_start_charge = self.outage_min_charge = s.charge
            self.outage_energy0 = self.energy_kwh
            return [("queda", {"carga": s.charge, "autonomia_s": s.runtime})]
        if on_battery and self.outage_start is not None:
            if s.charge is not None:
                self.outage_min_charge = min(self.outage_min_charge if self.outage_min_charge is not None else s.charge, s.charge)
            return []
        if not on_battery and self.outage_start is not None:
            seconds = round((now - self.outage_start).total_seconds())
            entry = {
                "inicio": self.outage_start.isoformat(),
                "fim": now.isoformat(),
                "segundos": seconds,
                "carga_inicial": self.outage_start_charge,
                "carga_minima": self.outage_min_charge,
                "energia_kwh": round(self.energy_kwh - (self.outage_energy0 or self.energy_kwh), 4),
            }
            self.outage_log = [*self.outage_log, entry][-MAX_LOG:]
            self.last_outage_seconds = seconds
            self.outage_start = self.outage_start_charge = self.outage_min_charge = self.outage_energy0 = None
            return [("retorno", {"duracao_s": seconds, "carga_minima": entry["carga_minima"]})]
        return []

    def _discharge(self, s: Sample, on_battery: bool) -> list[Event]:
        """Every stretch on battery (outage or self-test) measures the battery."""
        if on_battery:
            if self.dis_start is None:
                self.dis_start, self.dis_charge0, self.dis_runtime0 = s.now, s.charge, s.runtime
                self.dis_energy0, self.dis_min_charge = self.energy_kwh, s.charge
            elif s.charge is not None:
                self.dis_min_charge = min(self.dis_min_charge if self.dis_min_charge is not None else s.charge, s.charge)
            return []
        if self.dis_start is None:
            return []
        seconds = (s.now - self.dis_start).total_seconds()
        charge0, runtime0, low = self.dis_charge0, self.dis_runtime0, self.dis_min_charge
        energy = self.energy_kwh - (self.dis_energy0 or self.energy_kwh)
        self.dis_start = self.dis_charge0 = self.dis_runtime0 = self.dis_energy0 = self.dis_min_charge = None
        drop = (charge0 or 0) - (low if low is not None else charge0 or 0)
        if seconds < MIN_MEASURE_SECONDS or drop < MIN_MEASURE_DROP or not charge0 or not runtime0:
            return []
        # ponytail: health = discharge rate the UPS itself predicted (charge / runtime
        # estimate at the start) over the rate observed; the % gauge is not linear,
        # so it is a trend indicator, not a lab capacity test
        observed = drop / (seconds / 60)
        expected = charge0 / (runtime0 / 60)
        self.rate = round(observed, 3)
        self.rate_power = round(energy * 3_600_000 / seconds, 1) if energy > 0 else None
        self.health = round(min(150.0, 100 * expected / observed), 1)
        self.measured_at, self.measured_seconds, self.measured_drop = s.now, round(seconds), round(drop, 1)
        return [("medicao_bateria", {"saude": self.health, "taxa_pct_min": self.rate, "duracao_s": round(seconds)})]

    def _tests(self, s: Sample) -> list[Event]:
        result, now = s.test_result, s.now
        recorded = False
        finished = bool(result) and result.startswith(FINISHED_TEST)
        if self._test_started is not None:
            self._test_progress |= result == "In progress"
            # the old result is still shown right after the request; a quick test
            # can finish between two polls, so after QUICK_TEST an unchanged
            # "Done ..." is taken as the new result
            if finished and (
                result != self._test_baseline or self._test_progress or now - self._test_started >= QUICK_TEST
            ):
                recorded = True
                self._test_started = None
            elif now - self._test_started > TEST_TIMEOUT:
                self._test_started = None
        elif finished and self._seen_result is not None and result != self._seen_result:
            recorded = True  # started elsewhere: front panel or the UPS's own periodic test
        self._seen_result = result
        if not recorded:
            return []
        self.last_test, self.last_test_result = now, result
        return [("autoteste", {"resultado": result})]

    # ── persistence ────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        data = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        return {k: v.isoformat() if isinstance(v, datetime) else v for k, v in data.items()}

    @classmethod
    def from_dict(cls, data: dict) -> Tracker:
        names = {f for f in cls.__dataclass_fields__ if not f.startswith("_")}
        kwargs = {k: v for k, v in data.items() if k in names}
        for key in DATETIME_FIELDS:
            if kwargs.get(key):
                kwargs[key] = datetime.fromisoformat(kwargs[key])
        return cls(**kwargs)
