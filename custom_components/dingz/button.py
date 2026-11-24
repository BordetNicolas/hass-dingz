"""Button platform for Dingz."""

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import capabilities
from .coordinator import DingzConfigEntry, DingzRuntime
from .entity import DingzEntity, async_command, entity_unique_id

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data
    entities: list[ButtonEntity] = [
        Action(
            runtime,
            ButtonEntityDescription(
                key="save_default_config",
                entity_category=EntityCategory.CONFIG,
                translation_key="save_default_config",
            ),
            refresh_state=True,
        ),
        Action(
            runtime,
            ButtonEntityDescription(
                key="reboot",
                device_class=ButtonDeviceClass.RESTART,
                entity_category=EntityCategory.DIAGNOSTIC,
                translation_key="reboot",
            ),
        ),
    ]

    for index in capabilities.enabled_pirs(runtime.coordinator.data or {}):
        entities.append(ResetPirTime(runtime, index=index))

    async_add_entities(entities)


class Action(DingzEntity, ButtonEntity):
    def __init__(
        self,
        runtime: DingzRuntime,
        desc: ButtonEntityDescription,
        *,
        refresh_state: bool = False,
        refresh_config: bool = False,
    ) -> None:
        super().__init__(runtime.coordinator)
        self._attr_unique_id = entity_unique_id(runtime, desc.key)
        self._attr_device_info = runtime.device_info
        self.entity_description = desc
        self._refresh_state = refresh_state
        self._refresh_config = refresh_config

    async def async_press(self) -> None:
        method = getattr(self.runtime.client, self.entity_description.key)
        await async_command(method())

        if self._refresh_state:
            await self.runtime.coordinator.async_request_refresh()
        if self._refresh_config:
            await async_command(self.runtime.coordinator.async_refresh_config())


class ResetPirTime(DingzEntity, ButtonEntity):
    def __init__(self, runtime: DingzRuntime, index: int) -> None:
        super().__init__(runtime.coordinator)
        self._index = index
        self._attr_unique_id = entity_unique_id(runtime, f"reset_pir_{index}")
        self._attr_device_info = runtime.device_info
        self._attr_translation_key = f"reset_pir_time_{index}"

    async def async_press(self) -> None:
        await async_command(self.runtime.client.reset_pir_time(self._index))
        await self.runtime.coordinator.async_request_refresh()
