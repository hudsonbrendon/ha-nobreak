"""NUT client against the fake upsd, and the outage/energy/self-test tracker."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.nobreak.nut import NutClient, NutError
from custom_components.nobreak.tracker import Tracker, real_power


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


def test_tracker_outage_energy_and_tests() -> None:
    t0 = datetime(2026, 11, 23, 12, tzinfo=UTC)
    s = timedelta(seconds=10)
    tr = Tracker()
    tr.update(t0, {"OL"}, 180.0, "No test initiated")
    tr.update(t0 + s, {"OL"}, 180.0, "No test initiated")
    assert tr.energy_kwh == pytest.approx(180 * 10 / 3_600_000)

    # real outage: 30 s on battery
    tr.update(t0 + 2 * s, {"OB", "DISCHRG"}, 180.0, "No test initiated")
    tr.update(t0 + 5 * s, {"OB", "DISCHRG"}, 180.0, "No test initiated")
    assert tr.outages == 1 and tr.outage_duration(t0 + 5 * s) == 30
    tr.update(t0 + 6 * s, {"OL", "CHRG"}, 180.0, "No test initiated")
    assert tr.last_outage == t0 + 2 * s and tr.last_outage_seconds == 40
    assert tr.battery_seconds == 30

    # self-test we started: OB is not an outage; old "Done" is not the new result
    tr._seen_result = "Done and passed"
    now = t0 + 10 * s
    tr.expect_test(now, "Done and passed")
    tr.update(now + timedelta(seconds=1), {"OB"}, 180.0, "Done and passed")
    assert tr.outages == 1 and tr.last_test is None
    tr.update(now + timedelta(seconds=40), {"OL"}, 180.0, "Done and passed")
    assert tr.last_test == now + timedelta(seconds=40)

    # gap longer than MAX_GAP is not integrated
    e = tr.energy_kwh
    tr.update(now + timedelta(hours=1), {"OL"}, 180.0, "Done and passed")
    assert tr.energy_kwh == e

    restored = Tracker.from_dict(tr.to_dict())
    assert (restored.outages, restored.last_test, restored.energy_kwh) == (1, tr.last_test, e)
