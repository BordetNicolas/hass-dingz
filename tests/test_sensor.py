"""Sensor, binary sensor and event entity tests."""

from unittest.mock import MagicMock

from custom_components.dingz.binary_sensor import Input, Motion
from custom_components.dingz.event import Button
from custom_components.dingz.light import Dimmer
from custom_components.dingz.sensor import Brightness, OutputPower
from tests.fixtures.payloads import DINGZ_ID, full_device_config, state_payload


def _runtime(*, mqtt_enable: bool = False) -> MagicMock:
    runtime = MagicMock()
    runtime.dingz_id = DINGZ_ID
    runtime.device_info = {}
    coordinator = MagicMock()
    coordinator.data = state_payload()
    coordinator.device_config = full_device_config(mqtt_enable=mqtt_enable)
    coordinator.runtime = runtime
    runtime.coordinator = coordinator
    runtime.device_config = coordinator.device_config
    return runtime


def test_temperature_and_power_sensors() -> None:
    runtime = _runtime()
    power = OutputPower(runtime.coordinator, index=0)
    assert power.native_value == 12
    assert power.unique_id == f"{DINGZ_ID}_output_power_0"

    brightness = Brightness(runtime)
    brightness.handle_state_update()
    assert brightness.native_value == 123


def test_inactive_output_not_a_light() -> None:
    runtime = _runtime()
    outputs = runtime.coordinator.device_config.outputs
    active_lights = [
        index
        for index, output in enumerate(outputs)
        if output.get("active") and output.get("type") == "light"
    ]
    assert 3 not in active_lights
    assert Dimmer(runtime, 0).unique_id == f"{DINGZ_ID}_output_0"


def test_motion_and_input() -> None:
    runtime = _runtime()
    motion = Motion(runtime, index=0)
    motion.handle_state_update()
    assert motion.is_on is False
    assert motion.unique_id == f"{DINGZ_ID}_pir_0"

    contact = Input(runtime, index=0)
    contact.handle_state_update()
    assert contact.is_on is True


def test_button_event_unique_id() -> None:
    runtime = _runtime(mqtt_enable=True)
    button = Button(runtime, 0)
    assert button.unique_id == f"{DINGZ_ID}_button_0"
    assert button.user_given_name == "Btn1"
