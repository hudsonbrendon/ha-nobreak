"""Derived history the UPS does not keep: energy, outages, time on battery, self-tests.

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


@dataclass
class Tracker:
    energy_kwh: float = 0.0
    outages: int = 0
    last_outage: datetime | None = None
    last_outage_seconds: float | None = None
    outage_start: datetime | None = None
    battery_seconds: float = 0.0
    last_test: datetime | None = None
    last_test_result: str | None = None
    _test_started: datetime | None = field(default=None, repr=False)
    _test_baseline: str | None = field(default=None, repr=False)
    _test_progress: bool = field(default=False, repr=False)
    _prev: tuple[datetime, float | None, bool] | None = field(default=None, repr=False)
    _seen_result: str | None = field(default=None, repr=False)

    def expect_test(self, now: datetime, current_result: str | None) -> None:
        """A battery test was just requested: record its result, ignore its OB."""
        self._test_started, self._test_baseline, self._test_progress = (
            now,
            current_result,
            False,
        )

    def _in_test(self, now: datetime, result: str | None) -> bool:
        if result == "In progress":
            return True
        return self._test_started is not None and now - self._test_started < TEST_GRACE

    def outage_duration(self, now: datetime) -> float | None:
        if self.outage_start is not None:
            return round((now - self.outage_start).total_seconds())
        return self.last_outage_seconds

    def update(
        self,
        now: datetime,
        status: set[str],
        power: float | None,
        test_result: str | None,
    ) -> None:
        on_battery = "OB" in status
        if self._prev is not None:
            then, prev_power, was_on_battery = self._prev
            dt = (now - then).total_seconds()
            if 0 < dt <= MAX_GAP.total_seconds():
                if prev_power is not None and power is not None:
                    self.energy_kwh += (prev_power + power) / 2 * dt / 3_600_000
                if was_on_battery and on_battery:
                    self.battery_seconds += dt
        self._prev = (now, power, on_battery)

        if on_battery and self.outage_start is None and not self._in_test(now, test_result):
            self.outages += 1
            self.last_outage = self.outage_start = now
        elif not on_battery and self.outage_start is not None:
            self.last_outage_seconds = round((now - self.outage_start).total_seconds())
            self.outage_start = None

        finished = bool(test_result) and test_result.startswith(FINISHED_TEST)
        if self._test_started is not None:
            self._test_progress |= test_result == "In progress"
            # the old result is still shown right after the request; a quick test
            # can finish between two polls, so after QUICK_TEST an unchanged
            # "Done ..." is taken as the new result
            if finished and (
                test_result != self._test_baseline
                or self._test_progress
                or now - self._test_started >= QUICK_TEST
            ):
                self.last_test, self.last_test_result = now, test_result
                self._test_started = None
            elif now - self._test_started > TEST_TIMEOUT:
                self._test_started = None
        elif finished and self._seen_result is not None and test_result != self._seen_result:
            # started elsewhere: front panel button or the UPS's own periodic test
            self.last_test, self.last_test_result = now, test_result
        self._seen_result = test_result

    def to_dict(self) -> dict:
        data = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        return {k: v.isoformat() if isinstance(v, datetime) else v for k, v in data.items()}

    @classmethod
    def from_dict(cls, data: dict) -> Tracker:
        names = {f for f in cls.__dataclass_fields__ if not f.startswith("_")}
        kwargs = {k: v for k, v in data.items() if k in names}
        for key in ("last_outage", "outage_start", "last_test"):
            if kwargs.get(key):
                kwargs[key] = datetime.fromisoformat(kwargs[key])
        return cls(**kwargs)
