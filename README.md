<p align="center">
  <img src="custom_components/nobreak/brand/logo@2x.png" alt="Nobreak (NUT)" height="128">
</p>

# Nobreak (NUT) for Home Assistant

[![Tests](https://github.com/hudsonbrendon/ha-nobreak/actions/workflows/tests.yml/badge.svg)](https://github.com/hudsonbrendon/ha-nobreak/actions/workflows/tests.yml)
[![Hassfest](https://github.com/hudsonbrendon/ha-nobreak/actions/workflows/hassfest.yml/badge.svg)](https://github.com/hudsonbrendon/ha-nobreak/actions/workflows/hassfest.yml)
[![HACS](https://github.com/hudsonbrendon/ha-nobreak/actions/workflows/validate.yml/badge.svg)](https://github.com/hudsonbrendon/ha-nobreak/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/hudsonbrendon/ha-nobreak?sort=semver)](https://github.com/hudsonbrendon/ha-nobreak/releases)
[![Downloads](https://img.shields.io/github/downloads/hudsonbrendon/ha-nobreak/total)](https://github.com/hudsonbrendon/ha-nobreak/releases)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.10.0%2B-18BCF2?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![License](https://img.shields.io/github/license/hudsonbrendon/ha-nobreak)](LICENSE)

The core **Network UPS Tools** integration shows what `upsd` reports, read
only. This one sits next to it (its own **Nobreak** device, linked to the
NUT one with "connected via") and adds what is missing:

- **Controls** for every writable upsd variable: input **sensitivity**
  (select), **low/high transfer voltages**, shutdown/startup **delays** and
  low-battery limits (numbers), the **battery date** stored in the UPS (date),
  and the **audible alarm** (switch).
- **Buttons** for quick/deep **self-test**, stop test, **front panel test**,
  mute alarm and cancel a pending shutdown.
- **Real power** (W, from `ups.realpower` or load % × nominal W), **energy**
  total / today / this month (kWh, Energy-dashboard ready) and its **cost**
  today / this month (price from the options or the Energy dashboard).
- **Battery health**: every stretch on battery (outage or self-test, ≥ 1 min
  and ≥ 2 % drop) compares the discharge rate the UPS itself predicted with
  the one observed → health %, discharge rate, and a **real runtime** (to empty
  and to the shutdown limit) scaled to the current load.
- **Outage history**: count, last outage, duration (live while on battery),
  total time on battery, the last 10 outages as attributes (start, end, charge
  before/after, energy drawn) and a **calendar** with one event per outage.
- **Grid quality today**: minimum / maximum input voltage, time outside the
  ANEEL "adequate" band (0.92–1.05 × nominal: 202–231 V at 220 V), AVR
  activations and outages today.
- **Event entity** (`queda`, `retorno`, `autoteste`, `medicao_bateria`,
  `economia`) for automations and the logbook.
- **Repairs**: replace battery, failed self-test, battery older than 3 years,
  battery health below 60 %.
- **Load shedding** (options + switch): stage 1 turns entities off after N
  minutes on battery, stage 2 at a battery charge; both only during real
  outages (never in a self-test) and optionally turned back on when power
  returns.
- **Actions**: `nobreak.comando` (allow-listed commands only) and
  `nobreak.definir_variavel` (writable upsd variables, `driver.*` excluded).
- **Last self-test** and its result, **battery age**.
- **Binary sensors** from `ups.status`: utility power, low battery, charging,
  replace battery, overload, AVR (boost/trim), shutdown scheduled.
- **Firmware**: APC HID units keep it in USB string descriptor 6, which the
  NUT driver never reads; when Home Assistant runs on the host the UPS is
  plugged into it is read once at startup (e.g. `BZ1500XLBI-181019`).

Pair it with **[Nobreak Card](https://github.com/hudsonbrendon/nobreak-card)**,
an animated Lovelace card (outlet → UPS → load drawing per state, stats,
outage/self-test history and every control above).

Commands that cut power to the outlets (`load.off`, `shutdown.reboot`,
`driver.killpower`...) are deliberately **not** exposed: on most installs the
UPS also powers Home Assistant itself.

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=hudsonbrendon&repository=ha-nobreak&category=integration)

1. Add this repository to HACS as a custom integration and install it.
2. Restart Home Assistant.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=nobreak)

## Configuration

| Field | Notes |
|---|---|
| Host / port | `a0d7b954-nut` / `3493` for the Network UPS Tools add-on. |
| Username / password | A NUT user with `instcmds: [all]` and `actions: [SET]`. Without them everything is read-only (`ERR ACCESS-DENIED`). |
| UPS name | Empty when upsd serves a single UPS. |

Add-on example:

```yaml
users:
  - username: homeassistant
    password: "..."
    instcmds: [all]
    actions: [SET]
```

Only variables that upsd lists as writable (`LIST RW`) and commands it lists
(`LIST CMD`) become entities, so what you get depends on the UPS and driver.
The UPS may silently clamp a value it does not accept; the entity always
shows the value read back.

## Options

| Option | Meaning |
|---|---|
| Energy price | Per kWh, for the cost sensors. Empty: the fixed grid price of the Energy dashboard. |
| Stage 1 / after | Entities turned off after N minutes on battery. |
| Stage 2 / at charge | Entities turned off when the battery reaches this %. |
| Turn back on | Turn the shed entities (only those that were on) back on when power returns. |

## Notes

- Battery health is a trend indicator: the UPS charge gauge is not linear and
  its runtime estimate assumes a healthy battery, which is exactly what makes
  the comparison useful.

- Outages and the energy counter are computed from 10 s polls and survive
  restarts. Gaps longer than 5 minutes are not integrated. A self-test
  started from the button is not counted as an outage; one started from the
  front panel may be.
- `battery.mfr.date` on many APC units comes unprogrammed (`2107/15/31`
  means `0xFFFF`); set **Battery date** when you replace the battery and
  **Battery age** starts counting.

## Tested with

APC Back-UPS **BZ1500XLBI-BR** (USB `051d:0002`, `usbhid-ups` / APC HID 0.101,
NUT 2.8.5 add-on 0.18.2).

## License

[MIT](LICENSE)
