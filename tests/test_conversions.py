"""Tests for Dingz <-> Home Assistant value conversions."""

from homeassistant.components.climate import HVACAction, HVACMode

from custom_components.dingz.conversions import (
    brightness_dingz_to_ha,
    brightness_ha_to_dingz,
    cover_moving_from_state,
    cover_position_from_state,
    cover_tilt_from_state,
    dingz_to_hvac_action,
    dingz_to_hvac_mode,
    hsv_to_led_color,
    optional_float,
    parse_hsv,
    transition_to_ramp_ms,
)
from custom_components.dingz.models import MotorMotion


def test_brightness_roundtrip() -> None:
    assert brightness_dingz_to_ha(0) == 0
    assert brightness_dingz_to_ha(100) == 255
    assert brightness_dingz_to_ha(80) == 204
    assert brightness_ha_to_dingz(0) == 0
    assert brightness_ha_to_dingz(255) == 100
    assert brightness_ha_to_dingz(204) == 80


def test_parse_hsv() -> None:
    assert parse_hsv("120;50;80") == (120, 50, 80)
    assert parse_hsv("bad") is None
    assert parse_hsv("1;2") is None


def test_hsv_to_led_color() -> None:
    assert hsv_to_led_color(120.0, 50.0, 255) == "120;50;100"


def test_transition_to_ramp_ms() -> None:
    assert transition_to_ramp_ms(None) == 10
    assert transition_to_ramp_ms(1.5) == 1500


def test_cover_state_firmware_2() -> None:
    blind = {"moving": "up", "position": 40, "lamella": 20}
    assert cover_position_from_state(blind) == 40
    assert cover_tilt_from_state(blind) == 20
    assert cover_moving_from_state(blind) == "up"


def test_cover_state_playground_schema() -> None:
    blind = {"current": {"blind": 10, "lamella": 5}}
    assert cover_position_from_state(blind) == 10
    assert cover_tilt_from_state(blind) == 5


def test_optional_float_rejects_bool() -> None:
    assert optional_float(21.5) == 21.5
    assert optional_float(0) == 0.0
    assert optional_float(False) is None
    assert optional_float(True) is None
    assert optional_float(None) is None
    assert optional_float("nope") is None


def test_hvac_mapping() -> None:
    assert dingz_to_hvac_mode("heating") == HVACMode.HEAT
    assert dingz_to_hvac_mode("cooling") == HVACMode.COOL
    assert dingz_to_hvac_mode("off") == HVACMode.OFF
    assert dingz_to_hvac_mode("nope") is None  # type: ignore[arg-type]
    assert dingz_to_hvac_action("heating") == HVACAction.HEATING
    assert dingz_to_hvac_action("off") == HVACAction.OFF


def test_motor_motion_parse() -> None:
    assert MotorMotion.parse(1) is MotorMotion.OPENING
    assert MotorMotion.parse("2") is MotorMotion.CLOSING
    assert MotorMotion.parse("x") is MotorMotion.UNKNOWN
    assert MotorMotion.parse(99) is MotorMotion.UNKNOWN
