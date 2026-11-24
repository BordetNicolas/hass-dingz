"""MQTT push handler tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.dingz.models import (
    ButtonNotification,
    InputStateNotification,
    LightStateNotification,
    MotorMotion,
    MotorStateNotification,
    PirNotification,
)
from custom_components.dingz.mqtt import _MqttHandler
from tests.fixtures.payloads import state_payload


def _msg(topic: str, payload: str) -> SimpleNamespace:
    return SimpleNamespace(topic=topic, payload=payload)


def _handler() -> tuple[_MqttHandler, MagicMock]:
    runtime = MagicMock()
    runtime.coordinator.data = state_payload()
    runtime.coordinator.async_patch_state = MagicMock()
    runtime.dispatch = MagicMock()
    return _MqttHandler(runtime), runtime


def test_mqtt_light_patches_coordinator() -> None:
    handler, runtime = _handler()
    handler.handle_light(
        _msg(
            "dingz/id/dz1f-pir/state/light/0",
            '{"turn":"off","brightness":10,"exception":0}',
        )
    )
    runtime.coordinator.async_patch_state.assert_called_once()
    patched = runtime.coordinator.async_patch_state.call_args[0][0]
    assert patched["dimmers"][0]["on"] is False
    assert patched["dimmers"][0]["output"] == 10
    notification = runtime.dispatch.call_args[0][0]
    assert isinstance(notification, LightStateNotification)
    assert notification.index == 0


def test_mqtt_motor_patches_coordinator() -> None:
    handler, runtime = _handler()
    handler.handle_motor(
        _msg(
            "dingz/id/dz1f-pir/state/motor/0",
            '{"position":90,"lamella":15,"motion":1}',
        )
    )
    patched = runtime.coordinator.async_patch_state.call_args[0][0]
    assert patched["blinds"][0]["position"] == 90
    assert patched["blinds"][0]["moving"] == "up"
    notification = runtime.dispatch.call_args[0][0]
    assert isinstance(notification, MotorStateNotification)
    assert notification.motion is MotorMotion.OPENING


def test_mqtt_button_event() -> None:
    handler, runtime = _handler()
    handler.handle_button(_msg("dingz/id/dz1f-pir/event/button/2", "m1"))
    notification = runtime.dispatch.call_args[0][0]
    assert isinstance(notification, ButtonNotification)
    assert notification.index == 2
    assert notification.event_type == "m1"


def test_mqtt_pir_and_input() -> None:
    handler, runtime = _handler()
    handler.handle_pir(_msg("dingz/id/dz1f-pir/event/pir/0", "s"))
    pir = runtime.dispatch.call_args[0][0]
    assert isinstance(pir, PirNotification)
    assert pir.index == 0
    assert pir.event_type == "s"

    handler.handle_input(_msg("dingz/id/dz1f-pir/state/input/4", "1"))
    contact = runtime.dispatch.call_args[0][0]
    assert isinstance(contact, InputStateNotification)
    assert contact.on is True


def test_mqtt_ignores_broken_json() -> None:
    handler, runtime = _handler()
    handler.handle_light(_msg("dingz/id/dz1f-pir/state/light/0", "not-json"))
    runtime.coordinator.async_patch_state.assert_not_called()
    runtime.dispatch.assert_not_called()


def _relative_state() -> dict:
    """Dimmers/motors whose relative index differs from the list position."""
    state = state_payload()
    state["dimmers"] = [
        {"on": False, "output": 0, "index": {"relative": 1, "absolute": 3}},
        {"on": False, "output": 0, "index": {"relative": 0, "absolute": 2}},
    ]
    state["blinds"] = [
        {"position": 0, "lamella": 0, "index": {"relative": 0, "absolute": 1}}
    ]
    return state


def test_light_patch_targets_relative_index() -> None:
    handler, runtime = _handler()
    runtime.coordinator.data = _relative_state()
    handler.handle_light(
        _msg("dingz/id/m/state/light/0", '{"turn":"on","brightness":55,"exception":0}')
    )
    patched = runtime.coordinator.async_patch_state.call_args[0][0]
    assert patched["dimmers"][1] == {
        "on": True,
        "output": 55,
        "index": {"relative": 0, "absolute": 2},
    }
    assert patched["dimmers"][0]["on"] is False


def test_light_unknown_index_is_ignored_but_dispatched() -> None:
    handler, runtime = _handler()
    handler.handle_light(
        _msg("dingz/id/m/state/light/9", '{"turn":"on","brightness":5,"exception":0}')
    )
    runtime.coordinator.async_patch_state.assert_not_called()
    runtime.dispatch.assert_called_once()


def test_light_incomplete_payload() -> None:
    handler, runtime = _handler()
    handler.handle_light(_msg("dingz/id/m/state/light/0", '{"turn":"maybe"}'))
    runtime.dispatch.assert_not_called()


def test_motor_firmware_260_payload() -> None:
    handler, runtime = _handler()
    runtime.coordinator.data = _relative_state()
    handler.handle_motor(
        _msg(
            "dingz/id/m/state/motor/0",
            '{"motion":"2","position":30,"lamella":100,'
            '"target_position":0,"target_lamella":100}',
        )
    )
    notification = runtime.dispatch.call_args[0][0]
    assert notification.goal == 0
    assert notification.motion is MotorMotion.CLOSING
    patched = runtime.coordinator.async_patch_state.call_args[0][0]
    assert patched["blinds"][0]["moving"] == "down"
    assert patched["blinds"][0]["position"] == 30


def test_motor_incomplete_payload() -> None:
    handler, runtime = _handler()
    handler.handle_motor(_msg("dingz/id/m/state/motor/0", '{"motion":"0"}'))
    runtime.dispatch.assert_not_called()


def test_input_uses_index_4_only() -> None:
    """Firmware 2.6.0 publishes input/0 = 0 and input/4 = 1 for an active input."""
    handler, runtime = _handler()
    handler.handle_input(_msg("dingz/id/m/state/input/0", "0"))
    runtime.dispatch.assert_not_called()

    handler.handle_input(_msg("dingz/id/m/state/input/4", b"1"))
    notification = runtime.dispatch.call_args[0][0]
    assert isinstance(notification, InputStateNotification)
    assert notification.on is True
    patched = runtime.coordinator.async_patch_state.call_args[0][0]
    assert patched["sensors"]["input_state"] is True


def test_sensor_and_online() -> None:
    handler, runtime = _handler()
    handler.handle_sensor(_msg("dingz/id/m/sensor/temperature", "21.5"))
    patched = runtime.coordinator.async_patch_state.call_args[0][0]
    assert patched["sensors"]["room_temperature"] == 21.5
    handler.handle_sensor(_msg("dingz/id/m/sensor/light", "bad"))
    handler.handle_sensor(_msg("dingz/id/m/sensor/humidity", "1"))
    assert runtime.dispatch.call_count == 1

    handler.handle_online(_msg("dingz/id/online", "true"))
    assert runtime.dispatch.call_args[0][0].online is True


def test_no_state_yet_is_tolerated() -> None:
    handler, runtime = _handler()
    runtime.coordinator.data = None
    handler.handle_sensor(_msg("dingz/id/m/sensor/light", "12"))
    runtime.coordinator.async_patch_state.assert_not_called()


def test_topic_without_index() -> None:
    handler, runtime = _handler()
    handler.handle_button(_msg("dingz/id/m/event/button/x", "m1"))
    handler.handle_pir(_msg("dingz/id/m/event/pir/x", "s"))
    handler.handle_motor(_msg("dingz/id/m/state/motor/x", "{}"))
    runtime.dispatch.assert_not_called()
