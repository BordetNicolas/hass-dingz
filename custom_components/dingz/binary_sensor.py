"""Binary sensor platform for Dingz."""

import contextlib

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import api
from .coordinator import DingzConfigEntry, DingzRuntime
from .entity import (
    CoordinatedNotificationStateEntity,
    InternalNotificationMixin,
    UserAssignedNameMixin,
    entity_unique_id,
)
from .models import (
    InputStateNotification,
    InternalNotification,
    MqttOnlineNotification,
    PirNotification,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data
    entities: list[BinarySensorEntity] = [MqttOnline(runtime)]

    for index, dingz_input in enumerate(runtime.device_config.inputs):
        if dingz_input.get("active", False):
            entities.append(Input(runtime, index=index))

    try:
        pirs = runtime.coordinator.data["sensors"]["pirs"]
    except LookupError:
        pirs = []
    for index, dingz_pir in enumerate(pirs):
        if dingz_pir and dingz_pir.get("enabled", False):
            entities.append(Motion(runtime, index=index))

    async_add_entities(entities)


class Input(
    CoordinatedNotificationStateEntity,
    BinarySensorEntity,
    UserAssignedNameMixin,
):
    _attr_translation_key = "input"

    def __init__(self, runtime: DingzRuntime, *, index: int) -> None:
        super().__init__(runtime)
        self._index = index
        self._attr_unique_id = entity_unique_id(runtime, f"input_{index}")
        self._attr_device_info = runtime.device_info

    @property
    def dingz_input_config(self) -> api.InputConfig:
        try:
            return self.coordinator.device_config.inputs[self._index]
        except LookupError:
            return api.InputConfig()

    @property
    def comp_index(self) -> int:
        return self._index

    @property
    def user_given_name(self) -> str | None:
        return self.dingz_input_config.get("name")

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        try:
            input_ty = self.dingz_input_config["input"]["type"]
        except LookupError:
            return None

        if input_ty.startswith("pir_"):
            return BinarySensorDeviceClass.MOTION
        if input_ty == "garage_door_state":
            return BinarySensorDeviceClass.GARAGE_DOOR
        return BinarySensorDeviceClass.POWER

    @callback
    def handle_notification(self, notification: InternalNotification) -> None:
        if not (
            isinstance(notification, InputStateNotification)
            and notification.index == self._index
        ):
            return
        self._attr_is_on = notification.on
        self.async_write_ha_state()

    @callback
    def handle_state_update(self) -> None:
        with contextlib.suppress(LookupError):
            self._attr_is_on = self.coordinator.data["sensors"]["input_state"]


class Motion(CoordinatedNotificationStateEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(self, runtime: DingzRuntime, *, index: int) -> None:
        super().__init__(runtime)
        self._index = index
        self._motion: bool | None = None
        self._attr_unique_id = entity_unique_id(runtime, f"pir_{index}")
        self._attr_device_info = runtime.device_info
        self._attr_translation_key = f"motion_{index}"

    @callback
    def handle_notification(self, notification: InternalNotification) -> None:
        if not (
            isinstance(notification, PirNotification)
            and notification.index == self._index
        ):
            return
        self._motion = notification.event_type != "n"
        self.async_write_ha_state()

    @callback
    def handle_state_update(self) -> None:
        self._motion = self.dingz_pir.get("motion")

    @property
    def dingz_pir(self) -> api.SensorPir:
        try:
            raw = self.coordinator.data["sensors"]["pirs"][self._index]
        except LookupError:
            return api.SensorPir()
        if raw is None:
            return api.SensorPir()
        return raw

    @property
    def is_on(self) -> bool | None:
        return self._motion


class MqttOnline(InternalNotificationMixin, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "mqtt_online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime: DingzRuntime) -> None:
        super().__init__(runtime)
        self._online = False
        self._attr_unique_id = entity_unique_id(runtime, "mqtt_online")
        self._attr_device_info = runtime.device_info

    @callback
    def handle_notification(self, notification: InternalNotification) -> None:
        if not isinstance(notification, MqttOnlineNotification):
            return
        self._online = notification.online
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        return self._online
