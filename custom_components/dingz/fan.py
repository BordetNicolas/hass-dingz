"""Fan platform for Dingz."""

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DingzConfigEntry, DingzCoordinator
from .entity import DelayedCoordinatorRefreshMixin, DingzOutputEntity, entity_unique_id


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data
    entities: list[FanEntity] = []

    for index, dingz_output in enumerate(runtime.device_config.outputs):
        if dingz_output.get("active", False) and dingz_output.get("type") == "fan":
            entities.append(Fan(runtime.coordinator, index=index))

    async_add_entities(entities)


class Fan(
    DingzOutputEntity,
    FanEntity,
    DelayedCoordinatorRefreshMixin,
):
    _attr_translation_key = "fan"

    def __init__(self, coordinator: DingzCoordinator, *, index: int) -> None:
        super().__init__(coordinator, index=index)
        self._attr_unique_id = entity_unique_id(coordinator.runtime, f"fan_{index}")
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
        await self.runtime.client.set_dimmer(self.comp_index, "on")
        await self.delayed_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.runtime.client.set_dimmer(self.comp_index, "off")
        await self.delayed_request_refresh()
