"""Constants for the Dingz integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "dingz"

CONF_BASE_URL: Final = "base_url"

MANUFACTURER: Final = "iolo AG"

# One grouped GET /api/v1/state per cycle. Compatible with the device's 200 ms
# request throttle and Home Assistant polling guidance.
SCAN_INTERVAL: Final = timedelta(seconds=10)
DIAGNOSTIC_SCAN_INTERVAL: Final = timedelta(seconds=60)

REQUEST_TIMEOUT: Final = 10.0
REQUEST_THROTTLE: Final = 0.2

# The device needs a moment before GET /state reflects a command.
COMMAND_REFRESH_DELAY: Final = 1.0

GET_ATTEMPTS: Final = 5
GET_RETRY_DELAY: Final = 1.0
POST_ATTEMPTS: Final = 3
POST_RETRY_DELAY: Final = 3.0
