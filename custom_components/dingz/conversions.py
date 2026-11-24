"""Conversions between Dingz API values and Home Assistant entity values."""

from collections.abc import Mapping
from typing import Any, Final

from homeassistant.components.climate.const import HVACAction, HVACMode

from . import api

# Documented ranges (playground v2): dimmer ``time`` 0.01-10.00 s,
# LED ``ramp`` 0-4095 ms.
DIMMER_TIME_MIN: Final = 0.01
DIMMER_TIME_MAX: Final = 10.0
LED_RAMP_MAX_MS: Final = 4095


def brightness_dingz_to_ha(value: float) -> int:
    """Convert a Dingz brightness (0-100) to Home Assistant (0-255)."""
    value = min(max(value, 0), 100)
    return round(255 * value / 100)


def brightness_ha_to_dingz(value: float) -> int:
    """Convert a Home Assistant brightness (0-255) to Dingz (0-100).

    Any non-zero brightness maps to at least 1 so that a dim request never
    turns into a request for 0 %.
    """
    value = min(max(value, 0), 255)
    if value == 0:
        return 0
    return max(1, round(100 * value / 255))


def parse_hsv(raw: str) -> tuple[int, int, int] | None:
    """Parse a Dingz LED HSV string ``H;S;V`` (0-359; 0-100; 0-100)."""
    try:
        parts = tuple(int(part) for part in raw.split(";"))
    except ValueError:
        return None
    if len(parts) != 3:
        return None
    return parts[0], parts[1], parts[2]


def hsv_to_led_color(hue: float, saturation: float, brightness_ha: int) -> str:
    """Build a Dingz LED HSV color string from HA HS + brightness."""
    return f"{int(hue)};{int(saturation)};{brightness_ha_to_dingz(brightness_ha)}"


def transition_to_ramp_ms(transition: float | None, default: float = 0.01) -> int:
    """Convert a Home Assistant transition (seconds) to a Dingz LED ramp (ms)."""
    seconds = default if transition is None else transition
    return min(max(int(1000 * seconds), 0), LED_RAMP_MAX_MS)


def transition_to_dimmer_time(transition: float | None) -> float | None:
    """Convert a Home Assistant transition to the dimmer ``time`` parameter."""
    if transition is None:
        return None
    return round(min(max(transition, DIMMER_TIME_MIN), DIMMER_TIME_MAX), 2)


def _percent(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(min(max(value, 0), 100))


def _blind_value(blind: Mapping[str, Any], key: str, current_key: str) -> int | None:
    if (value := _percent(blind.get(key))) is not None:
        return value
    current = blind.get("current")
    if isinstance(current, Mapping):
        return _percent(current.get(current_key))
    return None


def cover_position_from_state(blind: Mapping[str, Any]) -> int | None:
    """Return cover position (0=closed, 100=open) from a Dingz blind state.

    Firmware 2.x uses ``position``. The official playground still documents
    ``current.blind``; both are accepted.
    """
    return _blind_value(blind, "position", "blind")


def cover_tilt_from_state(blind: Mapping[str, Any]) -> int | None:
    """Return slat/lamella position (0=closed, 100=open) from a Dingz blind state."""
    return _blind_value(blind, "lamella", "lamella")


def cover_moving_from_state(blind: Mapping[str, Any]) -> str | None:
    """Return ``up``, ``down`` or ``stop`` from a Dingz blind state."""
    moving = blind.get("moving")
    return moving if isinstance(moving, str) else None


def optional_float(value: Any) -> float | None:
    """Coerce a Dingz numeric field to float, treating booleans as missing.

    Some firmware payloads use ``false`` instead of omitting a temperature.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def dingz_to_hvac_mode(value: api.ThermostatModeEnum) -> HVACMode | None:
    """Map a Dingz thermostat mode to a Home Assistant HVAC mode."""
    match value:
        case "cooling":
            return HVACMode.COOL
        case "heating":
            return HVACMode.HEAT
        case "off":
            return HVACMode.OFF
        case _:
            return None


def dingz_to_hvac_action(value: api.ThermostatStateEnum) -> HVACAction | None:
    """Map a Dingz thermostat state to a Home Assistant HVAC action."""
    match value:
        case "cooling":
            return HVACAction.COOLING
        case "heating":
            return HVACAction.HEATING
        case "off":
            return HVACAction.OFF
        case _:
            return None
