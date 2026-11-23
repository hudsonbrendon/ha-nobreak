"""NUT client against the fake upsd, and the outage/energy/self-test tracker."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.nobreak.nut import NutClient, NutError
from custom_components.nobreak.tracker import Sample, Tracker, real_power


async def test_client_roundtrip(upsd) -> None:
    client = NutClient("127.0.0.1", upsd.port, "admin", "s3cret")
    assert await client.list_ups() == {"myups": "Description unavailable"}
    status, rw, cmds = await client.snapshot("myups")
    assert status["ups.model"] == "BZ1500XLBI-BR"
    assert "input.sensitivity" in rw and "test.battery.start.quick" in cmds

    await client.set_var("myups", "input.sensitivity", "high")
    assert (await client.list_vars("myups"))["input.sensitivity"] == "high"
    await client.run_command("myups", "beeper.mute")

    with pytest.raises(NutError, match="ACCESS-DENIED"):
        await NutClient("127.0.0.1", upsd.port, "admin", "wrong").run_command("myups", "beeper.mute")
    with pytest.raises(NutError):
        await client.set_var("myups", "input.sensitivity", 'x"\nINSTCMD myups load.off')
    with pytest.raises(NutError):
        await client.run_command("myups", "load.off\nX")


def test_real_power() -> None:
    assert real_power({"ups.load": "22", "ups.realpower.nominal": "825"}) == 181.5
    assert real_power({"ups.realpower": "100"}) == 100
    assert real_power({"ups.load": "22"}) is None


def S(t, status, power=180.0, test="No test initiated", charge=100.0, runtime=2100.0, voltage=216.0, day="2026-11-23"):
    return Sample(now=t, day=day, month=day[:7], status=status, power=power, test_result=test,
                  charge=charge, runtime=runtime, voltage=voltage, nominal_voltage=220.0)


def test_tracker_outage_energy_and_tests() -> None:
    t0 = datetime(2026, 11, 23, 12, tzinfo=UTC)
    s = timedelta(seconds=10)
    tr = Tracker()
    tr.update(S(t0, {"OL"}))
    tr.update(S(t0 + s, {"OL"}))
    assert tr.energy_kwh == pytest.approx(180 * 10 / 3_600_000)

    # real outage: 30 s on battery
    ev = tr.update(S(t0 + 2 * s, {"OB", "DISCHRG"}, charge=99))
    assert ev[0][0] == "queda"
    tr.update(S(t0 + 5 * s, {"OB", "DISCHRG"}, charge=97))
    assert tr.outages == 1 and tr.outage_duration(t0 + 5 * s) == 30
    ev = tr.update(S(t0 + 6 * s, {"OL", "CHRG"}, charge=97))
    assert [e[0] for e in ev] == ["retorno"]
    assert tr.last_outage == t0 + 2 * s and tr.last_outage_seconds == 40
    assert tr.battery_seconds == 30
    assert tr.outage_log[-1]["carga_inicial"] == 99 and tr.outage_log[-1]["carga_minima"] == 97
    assert tr.outages_day == 1

    # self-test we started: OB is not an outage; old "Done" is not the new result
    tr._seen_result = "Done and passed"
    now = t0 + 10 * s
    tr.expect_test(now, "Done and passed")
    tr.update(S(now + timedelta(seconds=1), {"OB"}, test="Done and passed"))
    assert tr.outages == 1 and tr.last_test is None
    ev = tr.update(S(now + timedelta(seconds=40), {"OL"}, test="Done and passed"))
    assert tr.last_test == now + timedelta(seconds=40) and ("autoteste", {"resultado": "Done and passed"}) in ev

    # gap longer than MAX_GAP is not integrated
    e = tr.energy_kwh
    tr.update(S(now + timedelta(hours=1), {"OL"}, test="Done and passed"))
    assert tr.energy_kwh == e

    restored = Tracker.from_dict(tr.to_dict())
    assert (restored.outages, restored.last_test, restored.energy_kwh) == (1, tr.last_test, e)
    assert restored.outage_log == tr.outage_log


def test_battery_health_from_a_discharge() -> None:
    """At 100 % the UPS predicts 35 min; dropping 20 % in 5 min means it empties in 25."""
    t0 = datetime(2026, 11, 23, 8, tzinfo=UTC)
    tr = Tracker()
    tr.update(S(t0, {"OL"}))
    tr.update(S(t0 + timedelta(seconds=10), {"OB"}, charge=100, runtime=2100))
    for i in range(1, 31):  # 5 minutes, 10 s polls, -2/3 % per poll
        tr.update(S(t0 + timedelta(seconds=10 + 10 * i), {"OB"}, charge=100 - 20 * i / 30, runtime=1800))
    ev = tr.update(S(t0 + timedelta(seconds=320), {"OL"}, charge=80))
    assert "medicao_bateria" in [e[0] for e in ev]
    rate = 20 / (310 / 60)  # the window runs until power is back
    assert tr.rate == pytest.approx(rate, rel=0.01)  # %/min
    assert tr.health == pytest.approx(100 * (100 / 35) / rate, rel=0.01)  # ~74 %
    assert tr.rate_power == pytest.approx(180, rel=0.02)
    # same power, 80 % left; twice the power halves the time
    assert tr.real_runtime(180, 80) == pytest.approx(80 / rate, rel=0.01)
    assert tr.real_runtime(180, 80, floor=30) == pytest.approx(50 / rate, rel=0.01)
    assert tr.real_runtime(360, 80) == pytest.approx(40 / rate, rel=0.01)


def test_short_discharge_is_not_measured() -> None:
    t0 = datetime(2026, 11, 23, 8, tzinfo=UTC)
    tr = Tracker()
    tr.update(S(t0, {"OB"}, charge=100))
    tr.update(S(t0 + timedelta(seconds=20), {"OL"}, charge=99))
    assert tr.health is None


def test_grid_quality_and_day_rollover() -> None:
    t0 = datetime(2026, 11, 23, 22, tzinfo=UTC)
    tr = Tracker()
    tr.update(S(t0, {"OL"}, voltage=216))
    tr.update(S(t0 + timedelta(seconds=10), {"OL"}, voltage=198))  # below 202.4
    tr.update(S(t0 + timedelta(seconds=20), {"OL", "BOOST"}, voltage=240))  # above 231
    tr.update(S(t0 + timedelta(seconds=30), {"OL"}, voltage=220))
    assert (tr.v_min, tr.v_max) == (198, 240)
    assert tr.out_of_range_seconds == 20 and tr.avr_count == 1
    assert tr.energy_today > 0
    tr.update(S(t0 + timedelta(seconds=40), {"OL"}, voltage=215, day="2026-11-24"))
    assert (tr.v_min, tr.v_max, tr.out_of_range_seconds, tr.avr_count) == (215, 215, 0, 0)
    assert tr.energy_today == 0
