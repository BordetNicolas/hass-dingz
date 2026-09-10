"""Optional MQTT push support using Home Assistant's MQTT integration."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any, cast

from homeassistant.components import mqtt
from homeassistant.components.mqtt.subscription import (
    async_prepare_subscribe_topics,
    async_subscribe_topics,
    async_unsubscribe_topics,
)

from .coordinator import DingzRuntime
from .models import (
    ButtonNotification,
    InputStateNotification,
    InternalNotification,
    LightStateNotification,
    MotorMotion,
    MotorStateNotification,
    MqttOnlineNotification,
    PirNotification,
    SimpleSensorStateNotification,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_mqtt(runtime: DingzRuntime) -> Callable[[], None] | None:
    """Subscribe to Dingz MQTT topics when HA MQTT is configured.

    REST remains the source of truth and the only command path. MQTT is a
    firmware push channel (topics are not part of the REST playground).
    """
    if not mqtt.mqtt_config_entry_enabled(runtime.hass):
        return None

    dingz_id = runtime.dingz_id
    if not dingz_id:
        _LOGGER.debug("skipping mqtt setup: dingz id unknown")
        return None

    _LOGGER.info("enabling mqtt integration for %s", dingz_id)
    handler = _MqttHandler(runtime)
    sub_state = async_prepare_subscribe_topics(
        runtime.hass,
        None,
        {
            "online": {
                "topic": f"dingz/{dingz_id}/online",
                "msg_callback": handler.handle_online,
            },
            "pir": {
                "topic": f"dingz/{dingz_id}/+/event/pir/+",
                "msg_callback": handler.handle_pir,
            },
            "button": {
                "topic": f"dingz/{dingz_id}/+/event/button/+",
                "msg_callback": handler.handle_button,
            },
            "motor": {
                "topic": f"dingz/{dingz_id}/+/state/motor/+",
                "msg_callback": handler.handle_motor,
            },
            "input": {
                "topic": f"dingz/{dingz_id}/+/state/input/+",
                "msg_callback": handler.handle_input,
            },
            "sensor": {
                "topic": f"dingz/{dingz_id}/+/sensor/+",
                "msg_callback": handler.handle_sensor,
            },
            "light": {
                "topic": f"dingz/{dingz_id}/+/state/light/+",
                "msg_callback": handler.handle_light,
            },
        },
    )
    await async_subscribe_topics(runtime.hass, sub_state)

    def unsub() -> None:
        async_unsubscribe_topics(runtime.hass, sub_state)

    return unsub


class _MqttHandler:
    def __init__(self, runtime: DingzRuntime) -> None:
        self.runtime = runtime

    def _dispatch(self, notification: InternalNotification) -> None:
        self.runtime.dispatch(notification)

    async def handle_online(self, msg: mqtt.ReceiveMessage) -> None:
        self._dispatch(MqttOnlineNotification(online=msg.payload == "true"))

    async def handle_pir(self, msg: mqtt.ReceiveMessage) -> None:
        index = _topic_index(msg.topic)
        if index is None:
            return
        self._dispatch(PirNotification(index=index, event_type=cast(Any, msg.payload)))

    async def handle_button(self, msg: mqtt.ReceiveMessage) -> None:
        index = _topic_index(msg.topic)
        if index is None:
            return
        self._dispatch(
            ButtonNotification(index=index, event_type=cast(Any, msg.payload))
        )

    async def handle_motor(self, msg: mqtt.ReceiveMessage) -> None:
        index = _topic_index(msg.topic)
        payload = _json_object(msg)
        if index is None or payload is None:
            return
        try:
            position = payload["position"]
            lamella = payload["lamella"]
        except KeyError:
            _LOGGER.error(
                "ignoring broken motor notification (topic = %s): %s",
                msg.topic,
                msg.payload,
            )
            return
        motion = MotorMotion.parse(payload.get("motion", MotorMotion.STOPPED))
        self._patch_blind(index, position=position, lamella=lamella, motion=motion)
        self._dispatch(
            MotorStateNotification(
                index=index,
                position=position,
                goal=payload.get("goal"),
                lamella=lamella,
                motion=motion,
            )
        )

    async def handle_sensor(self, msg: mqtt.ReceiveMessage) -> None:
        (_, _, sensor) = msg.topic.rpartition("/")
        try:
            value = float(msg.payload)
        except ValueError:
            _LOGGER.error(
                "ignoring broken sensor notification (topic = %s): %s",
                msg.topic,
                msg.payload,
            )
            return
        self._patch_sensor(cast(Any, sensor), value)
        self._dispatch(
            SimpleSensorStateNotification(sensor=cast(Any, sensor), value=value)
        )

    async def handle_input(self, msg: mqtt.ReceiveMessage) -> None:
        index = _topic_index(msg.topic)
        if index is None:
            return
        self._dispatch(InputStateNotification(index=index, on=msg.payload == "1"))

    async def handle_light(self, msg: mqtt.ReceiveMessage) -> None:
        index = _topic_index(msg.topic)
        payload = _json_object(msg)
        if index is None or payload is None:
            return
        try:
            turn = payload["turn"]
            brightness = payload["brightness"]
            exception = payload["exception"]
        except KeyError:
            _LOGGER.error(
                "ignoring broken light notification (topic = %s): %s",
                msg.topic,
                msg.payload,
            )
            return
        self._patch_dimmer(index, on=turn == "on", brightness=brightness)
        self._dispatch(
            LightStateNotification(
                index=index,
                turn=turn,
                brightness=brightness,
                exception=exception,
            )
        )

    def _replace_state(self, state: dict[str, Any]) -> None:
        self.runtime.coordinator.async_set_updated_data(cast(Any, state))

    def _patch_dimmer(self, index: int, *, on: bool, brightness: int) -> None:
        state = dict(self.runtime.coordinator.data)
        dimmers = list(state.get("dimmers") or [])
        if index >= len(dimmers):
            return
        dimmer = dict(dimmers[index])
        dimmer["on"] = on
        dimmer["output"] = brightness
        dimmers[index] = dimmer
        state["dimmers"] = dimmers
        self._replace_state(state)

    def _patch_blind(
        self,
        index: int,
        *,
        position: int,
        lamella: int,
        motion: MotorMotion,
    ) -> None:
        state = dict(self.runtime.coordinator.data)
        blinds = list(state.get("blinds") or [])
        if index >= len(blinds):
            return
        blind = dict(blinds[index])
        blind["position"] = position
        blind["lamella"] = lamella
        match motion:
            case MotorMotion.OPENING:
                blind["moving"] = "up"
            case MotorMotion.CLOSING:
                blind["moving"] = "down"
            case MotorMotion.STOPPED:
                blind["moving"] = "stop"
            case _:
                pass
        blinds[index] = blind
        state["blinds"] = blinds
        self._replace_state(state)

    def _patch_sensor(self, sensor: str, value: float) -> None:
        state = dict(self.runtime.coordinator.data)
        sensors = dict(state.get("sensors") or {})
        if sensor == "light":
            sensors["brightness"] = value
        elif sensor == "temperature":
            sensors["room_temperature"] = value
        else:
            return
        state["sensors"] = sensors
        self._replace_state(state)


def _topic_index(topic: str) -> int | None:
    (_, _, raw) = topic.rpartition("/")
    try:
        return int(raw)
    except ValueError:
        return None


def _json_object(msg: mqtt.ReceiveMessage) -> dict[str, Any] | None:
    try:
        payload: dict[str, Any] | Any = json.loads(msg.payload)
        if not isinstance(payload, dict):
            raise TypeError
    except (json.JSONDecodeError, TypeError):
        _LOGGER.error(
            "ignoring broken mqtt payload (topic = %s): %s",
            msg.topic,
            msg.payload,
        )
        return None
    return payload
