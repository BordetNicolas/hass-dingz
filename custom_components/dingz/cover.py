"""Cover platform for Dingz."""

from typing import Any

import voluptuous as vol
from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform, service
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import api, capabilities
from .const import DOMAIN
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
    async_command,
    clean_name,
    entity_unique_id,
)
from .models import InternalNotification, MotorMotion, MotorStateNotification

PARALLEL_UPDATES = 0

SERVICE_SET_POSITION_AND_TILT = "set_position_and_tilt"

_PERCENT = vol.All(vol.Coerce(int), vol.Range(min=0, max=100))
# Position and slats in a single command: the firmware chains both movements,
# whereas two separate calls would interrupt each other.
_SET_POSITION_AND_TILT_SCHEMA: dict[str | vol.Marker, Any] = {
    vol.Required(ATTR_POSITION): _PERCENT,
    vol.Required(ATTR_TILT_POSITION): _PERCENT,
}
# Home Assistant releases older than this helper register the action per
# platform instead (supported down to 2025.8).
_register_platform_entity_service = getattr(
    service, "async_register_platform_entity_service", None
)
_HAS_PLATFORM_ENTITY_SERVICE = _register_platform_entity_service is not None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data
    entities: list[CoverEntity] = []

    for slot in capabilities.blind_slots(runtime.coordinator.data or {}):
        if slot.readonly:
            continue
        # blind_config always lists both motors, indexed by absolute motor.
        cfg = capabilities.item_at(runtime.device_config.blinds, slot.absolute)
        if isinstance(cfg, dict) and not cfg.get("active", True):
            continue
        entities.append(Blind(runtime, slot=slot))

    async_add_entities(entities)

    if not _HAS_PLATFORM_ENTITY_SERVICE:
        entity_platform.async_get_current_platform().async_register_entity_service(
            SERVICE_SET_POSITION_AND_TILT,
            _SET_POSITION_AND_TILT_SCHEMA,
            "async_set_position_and_tilt",
        )


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration actions once, independently of config entries."""
    if _register_platform_entity_service is not None:
        _register_platform_entity_service(
            hass,
            DOMAIN,
            SERVICE_SET_POSITION_AND_TILT,
            entity_domain=Platform.COVER,
            schema=_SET_POSITION_AND_TILT_SCHEMA,
            func="async_set_position_and_tilt",
        )


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

    def __init__(self, runtime: DingzRuntime, *, slot: capabilities.Slot) -> None:
        super().__init__(runtime)
        self._slot = slot
        self._index = slot.relative
        self._blind_state: dict[str, Any] = {}
        # Historical unique id uses the relative motor index; keep it stable.
        self._attr_unique_id = entity_unique_id(runtime, f"cover_{slot.relative}")
        self._attr_device_info = runtime.device_info

    @property
    def dingz_blind_config(self) -> api.BlindConfig:
        item = capabilities.item_at(
            self.coordinator.device_config.blinds, self._slot.absolute
        )
        return item if item is not None else api.BlindConfig()

    @property
    def comp_index(self) -> int:
        return self._index

    @property
    def user_given_name(self) -> str | None:
        return clean_name(self.dingz_blind_config.get("name"))

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
        state = capabilities.find_by_absolute(
            (self.coordinator.data or {}).get("blinds"),
            self._slot.absolute,
            self._slot.relative,
        )
        if state is not None:
            self._blind_state = dict(state)

    async def async_open_cover(self, **kwargs: Any) -> None:
        await async_command(self.runtime.client.move_blind(self._index, "up"))
        await self.delayed_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        await async_command(self.runtime.client.move_blind(self._index, "down"))
        await self.delayed_request_refresh()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await async_command(self.runtime.client.move_blind(self._index, "stop"))
        await self.delayed_request_refresh()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await async_command(
            self.runtime.client.move_blind_position(
                self._index, blind=kwargs[ATTR_POSITION]
            )
        )
        await self.delayed_request_refresh()

    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        await async_command(
            self.runtime.client.move_blind_position(self._index, lamella=100)
        )
        await self.delayed_request_refresh()

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        await async_command(
            self.runtime.client.move_blind_position(self._index, lamella=0)
        )
        await self.delayed_request_refresh()

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        await async_command(
            self.runtime.client.move_blind_position(
                self._index, lamella=kwargs[ATTR_TILT_POSITION]
            )
        )
        await self.delayed_request_refresh()

    async def async_set_position_and_tilt(
        self, *, position: int, tilt_position: int
    ) -> None:
        await async_command(
            self.runtime.client.move_blind_position(
                self._index, blind=position, lamella=tilt_position
            )
        )
        await self.delayed_request_refresh()
