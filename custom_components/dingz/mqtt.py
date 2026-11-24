"""Optional MQTT push support using Home Assistant's MQTT integration.

Topics observed on firmware 2.4.3 and 2.6.0 (``<id>`` is the lower-case MAC,
``<model>`` the front model, e.g. ``dz1f-4b``):

- ``dingz/<id>/online`` (``true``/``false``), ``dingz/<id>/announce`` (JSON)
- ``dingz/<id>/<model>/state/light/<relative dimmer>`` (JSON)
- ``dingz/<id>/<model>/state/motor/<relative motor>`` (JSON)
- ``dingz/<id>/<model>/state/input/<n>`` (``0``/``1``)
- ``dingz/<id>/<model>/event/button/4`` (button connected to the input)
- ``dingz/<id>/<model>/sensor/<light|temperature>`` (number)
- ``dingz/<id>/<model>/power/<light|motor>/<relative index>`` (W)
- ``dingz/<id>/<model>/energy/<light|motor>/<relative index>`` (counter)
- ``dingz/<id>/<model>/event/<button|pir>/<n>`` (event code)

REST remains the source of truth and the only command path.
"""

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
from homeassistant.core import callback

from .const import (
    INPUT_BUTTON_TYPES,
    MQTT_INPUT_BUTTON_INDEX,
    MQTT_INPUT_STATE_INDEX,
)
from .coordinator import DingzRuntime
from .models import (
    ButtonNotification,
    EnergyNotification,
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
    """Subscribe to Dingz MQTT topics when HA MQTT is configured."""
    if not mqtt.mqtt_config_entry_enabled(runtime.hass):
        return None

    dingz_id = runtime.dingz_id
    if not dingz_id:
        _LOGGER.debug("skipping mqtt setup: dingz id unknown")
        return None

    _LOGGER.debug("enabling mqtt for %s", dingz_id)
    handler = _MqttHandler(runtime)
    base = f"dingz/{dingz_id}"
    sub_state = async_prepare_subscribe_topics(
        runtime.hass,
        None,
        {
            "online": {
                "topic": f"{base}/online",
                "msg_callback": handler.handle_online,
            },
            "pir": {
                "topic": f"{base}/+/event/pir/+",
                "msg_callback": handler.handle_pir,
            },
            "button": {
                "topic": f"{base}/+/event/button/+",
                "msg_callback": handler.handle_button,
            },
            "motor": {
                "topic": f"{base}/+/state/motor/+",
                "msg_callback": handler.handle_motor,
            },
            "input": {
                "topic": f"{base}/+/state/input/+",
                "msg_callback": handler.handle_input,
            },
            "sensor": {
                "topic": f"{base}/+/sensor/+",
                "msg_callback": handler.handle_sensor,
            },
            "light": {
                "topic": f"{base}/+/state/light/+",
                "msg_callback": handler.handle_light,
            },
            "energy": {
                "topic": f"{base}/+/energy/+/+",
                "msg_callback": handler.handle_energy,
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

    @callback
    def handle_online(self, msg: mqtt.ReceiveMessage) -> None:
        self._dispatch(MqttOnlineNotification(online=_text(msg) == "true"))

    @callback
    def handle_pir(self, msg: mqtt.ReceiveMessage) -> None:
        index = _topic_index(msg.topic)
        if index is None:
            return
        self._dispatch(PirNotification(index=index, event_type=cast(Any, _text(msg))))

    @callback
    def handle_button(self, msg: mqtt.ReceiveMessage) -> None:
        index = _topic_index(msg.topic)
        if index is None:
            return
        self._dispatch(
            ButtonNotification(index=index, event_type=cast(Any, _text(msg)))
        )

    @callback
    def handle_motor(self, msg: mqtt.ReceiveMessage) -> None:
        index = _topic_index(msg.topic)
        payload = _json_object(msg)
        if index is None or payload is None:
            return
        position = payload.get("position")
        lamella = payload.get("lamella")
        if not isinstance(position, int) or not isinstance(lamella, int):
            _LOGGER.debug("ignoring incomplete motor message on %s", msg.topic)
            return
        motion = MotorMotion.parse(payload.get("motion", MotorMotion.STOPPED))
        # Firmware 2.6.0 renamed ``goal`` to ``target_position``.
        goal = payload.get("target_position", payload.get("goal"))
        self._patch_blind(index, position=position, lamella=lamella, motion=motion)
        self._dispatch(
            MotorStateNotification(
                index=index,
                position=position,
                goal=goal if isinstance(goal, int) else None,
                lamella=lamella,
                motion=motion,
            )
        )

    @callback
    def handle_sensor(self, msg: mqtt.ReceiveMessage) -> None:
        (_, _, sensor) = msg.topic.rpartition("/")
        if sensor not in ("light", "temperature"):
            return
        value = _number(msg)
        if value is None:
            return
        self._patch_sensor(sensor, value)
        self._dispatch(
            SimpleSensorStateNotification(sensor=cast(Any, sensor), value=value)
        )

    @callback
    def handle_input(self, msg: mqtt.ReceiveMessage) -> None:
        if _topic_index(msg.topic) != self._input_topic_index():
            return
        on = _text(msg) == "1"
        self._patch_input(on)
        self._dispatch(InputStateNotification(index=0, on=on))

    @callback
    def handle_light(self, msg: mqtt.ReceiveMessage) -> None:
        index = _topic_index(msg.topic)
        payload = _json_object(msg)
        if index is None or payload is None:
            return
        turn = payload.get("turn")
        brightness = payload.get("brightness")
        if turn not in ("on", "off") or not isinstance(brightness, int | float):
            _LOGGER.debug("ignoring incomplete light message on %s", msg.topic)
            return
        self._patch_dimmer(index, on=turn == "on", brightness=int(brightness))
        self._dispatch(
            LightStateNotification(
                index=index,
                turn=turn,
                brightness=int(brightness),
                exception=payload.get("exception", 0),
            )
        )

    @callback
    def handle_energy(self, msg: mqtt.ReceiveMessage) -> None:
        levels = msg.topic.split("/")
        index = _topic_index(msg.topic)
        if index is None or len(levels) < 2 or levels[-2] not in ("light", "motor"):
            return
        value = _number(msg)
        if value is None or value < 0:
            return
        self._dispatch(
            EnergyNotification(kind=cast(Any, levels[-2]), index=index, value=value)
        )

    def _input_topic_index(self) -> int:
        inputs = self.runtime.device_config.inputs
        input_type = None
        if inputs and isinstance(inputs[0], dict):
            input_type = (inputs[0].get("input") or {}).get("type")
        if input_type in INPUT_BUTTON_TYPES:
            return MQTT_INPUT_BUTTON_INDEX
        return MQTT_INPUT_STATE_INDEX

    def _state(self) -> dict[str, Any] | None:
        data = self.runtime.coordinator.data
        return dict(data) if isinstance(data, dict) else None

    def _replace_state(self, state: dict[str, Any]) -> None:
        self.runtime.coordinator.async_patch_state(cast(Any, state))

    def _patch_list_item(
        self, key: str, relative: int, updates: dict[str, Any]
    ) -> None:
        state = self._state()
        if state is None:
            return
        items = list(state.get(key) or [])
        for position, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            item_relative = (
                index.get("relative", position) if isinstance(index, dict) else position
            )
            if item_relative == relative:
                items[position] = {**item, **updates}
                state[key] = items
                self._replace_state(state)
                return

    def _patch_dimmer(self, index: int, *, on: bool, brightness: int) -> None:
        self._patch_list_item("dimmers", index, {"on": on, "output": brightness})

    def _patch_blind(
        self,
        index: int,
        *,
        position: int,
        lamella: int,
        motion: MotorMotion,
    ) -> None:
        updates: dict[str, Any] = {"position": position, "lamella": lamella}
        match motion:
            case MotorMotion.OPENING:
                updates["moving"] = "up"
            case MotorMotion.CLOSING:
                updates["moving"] = "down"
            case MotorMotion.STOPPED:
                updates["moving"] = "stop"
            case _:
                pass
        self._patch_list_item("blinds", index, updates)

    def _patch_sensors(self, updates: dict[str, Any]) -> None:
        state = self._state()
        if state is None:
            return
        state["sensors"] = {**(state.get("sensors") or {}), **updates}
        self._replace_state(state)

    def _patch_sensor(self, sensor: str, value: float) -> None:
        key = "brightness" if sensor == "light" else "room_temperature"
        self._patch_sensors({key: value})

    def _patch_input(self, on: bool) -> None:
        self._patch_sensors({"input_state": on})


def _text(msg: mqtt.ReceiveMessage) -> str:
    payload = msg.payload
    if isinstance(payload, bytes | bytearray):
        return payload.decode(errors="replace")
    return str(payload)


def _number(msg: mqtt.ReceiveMessage) -> float | None:
    try:
        return float(_text(msg))
    except ValueError:
        _LOGGER.debug("ignoring non-numeric message on %s", msg.topic)
        return None


def _topic_index(topic: str) -> int | None:
    (_, _, raw) = topic.rpartition("/")
    try:
        return int(raw)
    except ValueError:
        return None


def _json_object(msg: mqtt.ReceiveMessage) -> dict[str, Any] | None:
    try:
        payload = json.loads(_text(msg))
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict):
        _LOGGER.debug("ignoring invalid mqtt payload on %s", msg.topic)
        return None
    return payload
