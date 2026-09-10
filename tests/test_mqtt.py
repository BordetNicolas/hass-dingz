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
    runtime.coordinator.async_set_updated_data = MagicMock()
    runtime.dispatch = MagicMock()
    return _MqttHandler(runtime), runtime


async def test_mqtt_light_patches_coordinator() -> None:
    handler, runtime = _handler()
    await handler.handle_light(
        _msg(
            "dingz/id/dz1f-pir/state/light/0",
            '{"turn":"off","brightness":10,"exception":0}',
        )
    )
    runtime.coordinator.async_set_updated_data.assert_called_once()
    patched = runtime.coordinator.async_set_updated_data.call_args[0][0]
    assert patched["dimmers"][0]["on"] is False
    assert patched["dimmers"][0]["output"] == 10
    notification = runtime.dispatch.call_args[0][0]
    assert isinstance(notification, LightStateNotification)
    assert notification.index == 0


async def test_mqtt_motor_patches_coordinator() -> None:
    handler, runtime = _handler()
    await handler.handle_motor(
        _msg(
            "dingz/id/dz1f-pir/state/motor/0",
            '{"position":90,"lamella":15,"motion":1}',
        )
    )
    patched = runtime.coordinator.async_set_updated_data.call_args[0][0]
    assert patched["blinds"][0]["position"] == 90
    assert patched["blinds"][0]["moving"] == "up"
    notification = runtime.dispatch.call_args[0][0]
    assert isinstance(notification, MotorStateNotification)
    assert notification.motion is MotorMotion.OPENING


async def test_mqtt_button_event() -> None:
    handler, runtime = _handler()
    await handler.handle_button(_msg("dingz/id/dz1f-pir/event/button/2", "m1"))
    notification = runtime.dispatch.call_args[0][0]
    assert isinstance(notification, ButtonNotification)
    assert notification.index == 2
    assert notification.event_type == "m1"


async def test_mqtt_pir_and_input() -> None:
    handler, runtime = _handler()
    await handler.handle_pir(_msg("dingz/id/dz1f-pir/event/pir/0", "s"))
    pir = runtime.dispatch.call_args[0][0]
    assert isinstance(pir, PirNotification)
    assert pir.index == 0
    assert pir.event_type == "s"

    await handler.handle_input(_msg("dingz/id/dz1f-pir/state/input/0", "1"))
    contact = runtime.dispatch.call_args[0][0]
    assert isinstance(contact, InputStateNotification)
    assert contact.on is True


async def test_mqtt_ignores_broken_json() -> None:
    handler, runtime = _handler()
    await handler.handle_light(_msg("dingz/id/dz1f-pir/state/light/0", "not-json"))
    runtime.coordinator.async_set_updated_data.assert_not_called()
    runtime.dispatch.assert_not_called()
