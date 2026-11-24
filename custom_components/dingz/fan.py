"""Fan platform for Dingz."""

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import capabilities
from .coordinator import DingzConfigEntry, DingzCoordinator
from .entity import (
    DelayedCoordinatorRefreshMixin,
    DingzOutputEntity,
    async_command,
    entity_unique_id,
    output_slots,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data
    entities: list[FanEntity] = []

    for slot in output_slots(runtime, "fan"):
        entities.append(Fan(runtime.coordinator, slot=slot))

    async_add_entities(entities)


class Fan(
    DingzOutputEntity,
    FanEntity,
    DelayedCoordinatorRefreshMixin,
):
    _attr_translation_key = "fan"

    def __init__(
        self, coordinator: DingzCoordinator, *, slot: capabilities.Slot
    ) -> None:
        super().__init__(coordinator, slot=slot)
        self._attr_unique_id = entity_unique_id(
            coordinator.runtime, f"fan_{slot.absolute}"
        )
        self._attr_supported_features = (
            FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        )

    @property
    def is_on(self) -> bool | None:
        return self.dingz_dimmer.get("on")

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        await async_command(self.runtime.client.set_dimmer(self._slot.relative, "on"))
        await self.delayed_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await async_command(self.runtime.client.set_dimmer(self._slot.relative, "off"))
        await self.delayed_request_refresh()
