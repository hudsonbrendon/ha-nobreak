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
