"""Event platform for Dingz."""

import logging

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import api, capabilities
from .coordinator import DingzConfigEntry, DingzRuntime
from .entity import (
    InternalNotificationMixin,
    UserAssignedNameMixin,
    clean_name,
    entity_unique_id,
)
from .models import ButtonNotification, InternalNotification, PirNotification

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data
    entities: list[EventEntity] = []

    if capabilities.mqtt_enabled(runtime.device_config):
        for index in capabilities.enabled_pirs(runtime.coordinator.data or {}):
            entities.append(Pir(runtime, index=index))

        try:
            buttons = runtime.device_config.buttons["buttons"]
        except LookupError:
            buttons = []
        for index, dingz_button in enumerate(buttons):
            if dingz_button.get("active", False):
                entities.append(Button(runtime, index=index))

    async_add_entities(entities)


class Pir(InternalNotificationMixin, EventEntity):
    _attr_has_entity_name = True
    _attr_device_class = EventDeviceClass.MOTION
    _attr_event_types = ["s", "ss", "n"]

    def __init__(self, runtime: DingzRuntime, index: int) -> None:
        super().__init__(runtime)
        self._index = index
        self._attr_unique_id = entity_unique_id(runtime, f"pir_event_{index}")
        self._attr_device_info = runtime.device_info
        self._attr_translation_key = f"pir_{index}"

    @callback
    def handle_notification(self, notification: InternalNotification) -> None:
        if not (
            isinstance(notification, PirNotification)
            and notification.index == self._index
        ):
            return
        _trigger(self, notification.event_type)


class Button(InternalNotificationMixin, EventEntity, UserAssignedNameMixin):
    _attr_translation_key = "button"
    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = ["p", "r", "h", "m1", "m2", "m3", "m4", "m5"]

    def __init__(self, runtime: DingzRuntime, index: int) -> None:
        super().__init__(runtime)
        self._index = index
        self._attr_unique_id = entity_unique_id(runtime, f"button_{index}")
        self._attr_device_info = runtime.device_info

    @property
    def dingz_button_config(self) -> api.ButtonConfig:
        try:
            return self.runtime.device_config.buttons["buttons"][self._index]
        except LookupError:
            return api.ButtonConfig()

    @property
    def comp_index(self) -> int:
        return self._index

    @property
    def user_given_name(self) -> str | None:
        return clean_name(self.dingz_button_config.get("name"))

    @callback
    def handle_notification(self, notification: InternalNotification) -> None:
        if not (
            isinstance(notification, ButtonNotification)
            and notification.index == self._index
        ):
            return
        _trigger(self, notification.event_type)


def _trigger(entity: EventEntity, event_type: str) -> None:
    """Fire an event, ignoring types the firmware may add in the future."""
    if event_type not in entity.event_types:
        _LOGGER.debug("ignoring unknown event type %r for %s", event_type, entity)
        return
    entity._trigger_event(event_type)
    entity.async_write_ha_state()
