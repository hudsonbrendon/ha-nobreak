"""Constants for the Nobreak (NUT) integration."""

from datetime import timedelta

DOMAIN = "nobreak"
CONF_UPS = "ups"
DEFAULT_HOST = "a0d7b954-nut"  # Network UPS Tools add-on
DEFAULT_PORT = 3493
SCAN_INTERVAL = timedelta(seconds=10)

# upsd identifies devices the same way as the core NUT integration, so the
# entities land on the device that integration already created.
NUT_DOMAIN = "nut"
NUT_FAKE_SERIAL = ("unknown", "blank")

# options
CONF_PRICE = "tarifa"
CONF_SHED1 = "economia_estagio1"
CONF_SHED1_DELAY = "economia_atraso"
CONF_SHED2 = "economia_estagio2"
CONF_SHED2_CHARGE = "economia_carga"
CONF_SHED_RESTORE = "economia_religar"
DEFAULT_SHED1_DELAY = 2  # minutes on battery
DEFAULT_SHED2_CHARGE = 50  # %

EVENT_TYPES = ["queda", "retorno", "autoteste", "medicao_bateria", "economia"]

# repairs
HEALTH_ISSUE_BELOW = 60  # % battery health
OLD_BATTERY_DAYS = 3 * 365
