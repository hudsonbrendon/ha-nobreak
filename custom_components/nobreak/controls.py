"""Which upsd variables and commands become entities.

Only allow-listed commands are exposed. load.off, shutdown.* (except stop)
and driver.killpower cut the outlets, which on a typical install also powers
off Home Assistant itself, so they never become buttons.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.const import PERCENTAGE, UnitOfElectricPotential, UnitOfTime


@dataclass(frozen=True)
class NumberVar:
    key: str
    var: str
    unit: str
    min: float
    max: float
    step: float = 1


# ponytail: upsd publishes no RANGE for these on APC HID units, so the bounds
# are the usual APC ones; the UPS clamps or ignores anything it does not take
# and the entity shows the value read back.
NUMBERS = (
    NumberVar("transferencia_baixa", "input.transfer.low", UnitOfElectricPotential.VOLT, 150, 200),
    NumberVar("transferencia_alta", "input.transfer.high", UnitOfElectricPotential.VOLT, 240, 290),
    NumberVar("atraso_desligamento", "ups.delay.shutdown", UnitOfTime.SECONDS, 0, 600),
    NumberVar("atraso_religamento", "ups.delay.start", UnitOfTime.SECONDS, 0, 600),
    NumberVar("carga_minima", "battery.charge.low", PERCENTAGE, 5, 95),
    NumberVar("autonomia_minima", "battery.runtime.low", UnitOfTime.SECONDS, 0, 3600, 10),
)

SENSITIVITY_VAR = "input.sensitivity"
SENSITIVITY_OPTIONS = ["low", "medium", "high"]

BATTERY_DATE_VAR = "battery.mfr.date"

BEEPER_ON = "beeper.enable"
BEEPER_OFF = "beeper.disable"

# key -> NUT command
BUTTONS = {
    "autoteste_rapido": "test.battery.start.quick",
    "autoteste_completo": "test.battery.start.deep",
    "parar_autoteste": "test.battery.stop",
    "testar_painel": "test.panel.start",
    "silenciar_alarme": "beeper.mute",
    "cancelar_desligamento": "shutdown.stop",
}

# Commands the nobreak.comando action accepts (never anything that cuts the outlets).
SAFE_COMMANDS = sorted(
    {
        *BUTTONS.values(),
        "test.panel.stop",
        "beeper.enable",
        "beeper.disable",
        "beeper.on",
        "beeper.off",
        "beeper.mute",
    }
)
