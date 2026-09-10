"""Internal notification types used for MQTT push updates."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Literal, Union


@dataclass(slots=True)
class InternalNotification: ...


@dataclass(slots=True, kw_only=True)
class MqttOnlineNotification(InternalNotification):
    online: bool


PirEventType = Literal["s", "ss", "n"]


@dataclass(slots=True, kw_only=True)
class PirNotification(InternalNotification):
    index: int
    event_type: PirEventType


ButtonEventType = Literal["p", "r", "h", "m1", "m2", "m3", "m4", "m5"]


@dataclass(slots=True, kw_only=True)
class ButtonNotification(InternalNotification):
    index: int
    event_type: ButtonEventType


class MotorMotion(IntEnum):
    UNKNOWN = -1
    STOPPED = 0
    OPENING = 1
    CLOSING = 2
    CALIBRATING = 3

    @classmethod
    def parse(cls, value: Union[str, int, "MotorMotion"]) -> "MotorMotion":
        if isinstance(value, MotorMotion):
            return value

        if not isinstance(value, int):
            try:
                value = int(value)
            except ValueError:
                return MotorMotion.UNKNOWN
        try:
            return MotorMotion(value)
        except ValueError:
            return MotorMotion.UNKNOWN


@dataclass(slots=True, kw_only=True)
class MotorStateNotification(InternalNotification):
    index: int
    position: int
    goal: int | None
    lamella: int
    motion: MotorMotion


@dataclass(slots=True, kw_only=True)
class SimpleSensorStateNotification(InternalNotification):
    sensor: Literal["light", "temperature"]
    value: float


@dataclass(slots=True, kw_only=True)
class InputStateNotification(InternalNotification):
    index: int
    on: bool


@dataclass(slots=True, kw_only=True)
class LightStateNotification(InternalNotification):
    index: int
    turn: Literal["on", "off"]
    brightness: int
    exception: int
