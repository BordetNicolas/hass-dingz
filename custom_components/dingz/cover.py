"""Cover platform for Dingz."""

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import api
from .conversions import (
    cover_moving_from_state,
    cover_position_from_state,
    cover_tilt_from_state,
)
from .coordinator import DingzConfigEntry, DingzRuntime
from .entity import (
    CoordinatedNotificationStateEntity,
    DelayedCoordinatorRefreshMixin,
    UserAssignedNameMixin,
    entity_unique_id,
)
from .models import InternalNotification, MotorMotion, MotorStateNotification


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data
    entities: list[CoverEntity] = []

    blinds = runtime.coordinator.data.get("blinds") or []
    for index, blind in enumerate(blinds):
        if blind.get("readonly"):
            continue
        try:
            cfg = runtime.device_config.blinds[index]
        except LookupError:
            cfg = api.BlindConfig()
        if cfg and not cfg.get("active", True):
            continue
        entities.append(Blind(runtime, index=index))

    async_add_entities(entities)


class Blind(
    CoordinatedNotificationStateEntity,
    CoverEntity,
    UserAssignedNameMixin,
    DelayedCoordinatorRefreshMixin,
):
    _attr_translation_key = "blind"
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
        | CoverEntityFeature.STOP
        | CoverEntityFeature.OPEN_TILT
        | CoverEntityFeature.CLOSE_TILT
        | CoverEntityFeature.SET_TILT_POSITION
    )

    def __init__(self, runtime: DingzRuntime, *, index: int) -> None:
        super().__init__(runtime)
        self._index = index
        self._blind_state: dict[str, Any] = {}
        self._attr_unique_id = entity_unique_id(runtime, f"cover_{index}")
        self._attr_device_info = runtime.device_info

    @property
    def dingz_blind_config(self) -> api.BlindConfig:
        try:
            return self.coordinator.device_config.blinds[self._index]
        except LookupError:
            return api.BlindConfig()

    @property
    def comp_index(self) -> int:
        return self._index

    @property
    def user_given_name(self) -> str | None:
        return self.dingz_blind_config.get("name")

    @property
    def current_cover_position(self) -> int | None:
        return cover_position_from_state(self._blind_state)

    @property
    def current_cover_tilt_position(self) -> int | None:
        return cover_tilt_from_state(self._blind_state)

    @property
    def is_opening(self) -> bool | None:
        return cover_moving_from_state(self._blind_state) == "up"

    @property
    def is_closing(self) -> bool | None:
        return cover_moving_from_state(self._blind_state) == "down"

    @property
    def is_closed(self) -> bool | None:
        if (pos := self.current_cover_position) is not None:
            return pos == 0
        return None

    @callback
    def handle_notification(self, notification: InternalNotification) -> None:
        if not (
            isinstance(notification, MotorStateNotification)
            and notification.index == self._index
        ):
            return

        self._blind_state["lamella"] = notification.lamella
        self._blind_state["position"] = notification.position
        match notification.motion:
            case MotorMotion.OPENING:
                self._blind_state["moving"] = "up"
            case MotorMotion.CLOSING:
                self._blind_state["moving"] = "down"
            case MotorMotion.STOPPED:
                self._blind_state["moving"] = "stop"
            case _:
                pass

        self.async_write_ha_state()

    @callback
    def handle_state_update(self) -> None:
        try:
            state = self.coordinator.data["blinds"][self._index]
        except LookupError:
            return
        self._blind_state = dict(state)

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self.runtime.client.move_blind(self._index, "up")
        await self.delayed_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self.runtime.client.move_blind(self._index, "down")
        await self.delayed_request_refresh()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self.runtime.client.move_blind(self._index, "stop")
        await self.delayed_request_refresh()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self.runtime.client.move_blind_position(
            self._index, blind=kwargs[ATTR_POSITION]
        )
        await self.delayed_request_refresh()

    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        await self.runtime.client.move_blind_position(self._index, lamella=100)
        await self.delayed_request_refresh()

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        await self.runtime.client.move_blind_position(self._index, lamella=0)
        await self.delayed_request_refresh()

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        await self.runtime.client.move_blind_position(
            self._index, lamella=kwargs[ATTR_TILT_POSITION]
        )
        await self.delayed_request_refresh()
