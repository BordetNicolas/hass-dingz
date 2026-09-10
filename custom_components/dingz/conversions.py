"""Conversions between Dingz API values and Home Assistant entity values."""

from collections.abc import Mapping
from typing import Any

from homeassistant.components.climate import HVACAction, HVACMode

from . import api


def brightness_dingz_to_ha(value: int) -> int:
    """Convert a Dingz brightness (0-100) to Home Assistant (0-255)."""
    return 255 * value // 100


def brightness_ha_to_dingz(value: int) -> int:
    """Convert a Home Assistant brightness (0-255) to Dingz (0-100)."""
    return 100 * value // 255


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
    return int(1000 * seconds)


def cover_position_from_state(blind: Mapping[str, Any]) -> int | None:
    """Return cover position (0=closed, 100=open) from a Dingz blind state.

    Firmware 2.x uses ``position``. The official playground still documents
    ``current.blind``; both are accepted.
    """
    if (position := blind.get("position")) is not None:
        return position
    current = blind.get("current")
    if isinstance(current, dict) and (position := current.get("blind")) is not None:
        return position
    return None


def cover_tilt_from_state(blind: Mapping[str, Any]) -> int | None:
    """Return slat/lamella position (0=closed, 100=open) from a Dingz blind state."""
    if (lamella := blind.get("lamella")) is not None:
        return lamella
    current = blind.get("current")
    if isinstance(current, dict) and (lamella := current.get("lamella")) is not None:
        return lamella
    return None


def cover_moving_from_state(blind: Mapping[str, Any]) -> str | None:
    """Return ``up``, ``down`` or ``stop`` from a Dingz blind state."""
    if (moving := blind.get("moving")) is not None:
        return moving
    return None


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
