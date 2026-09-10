"""Button platform for Dingz."""

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import api
from .coordinator import DingzConfigEntry, DingzRuntime
from .entity import entity_unique_id


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

    try:
        pirs = runtime.coordinator.data["sensors"]["pirs"]
    except LookupError:
        pirs = []
    for index, dingz_pir in enumerate(pirs):
        if dingz_pir and dingz_pir.get("enabled", False):
            entities.append(ResetPirTime(runtime, index=index))

    async_add_entities(entities)


class Action(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        runtime: DingzRuntime,
        desc: ButtonEntityDescription,
        *,
        refresh_state: bool = False,
        refresh_config: bool = False,
    ) -> None:
        self.runtime = runtime
        self._attr_unique_id = entity_unique_id(runtime, desc.key)
        self._attr_device_info = runtime.device_info
        self.entity_description = desc
        self._refresh_state = refresh_state
        self._refresh_config = refresh_config

    async def async_press(self) -> None:
        method = getattr(self.runtime.client, self.entity_description.key)
        await method()

        if self._refresh_state:
            await self.runtime.coordinator.async_request_refresh()
        if self._refresh_config:
            await self.runtime.coordinator.async_refresh_config()


class ResetPirTime(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, runtime: DingzRuntime, index: int) -> None:
        self.runtime = runtime
        self._index = index
        self._attr_unique_id = entity_unique_id(runtime, f"reset_pir_{index}")
        self._attr_device_info = runtime.device_info
        self._attr_translation_key = f"reset_pir_time_{index}"

    @property
    def dingz_pir(self) -> api.SensorPir:
        try:
            raw = self.runtime.coordinator.data["sensors"]["pirs"][self._index]
        except LookupError:
            return api.SensorPir()
        if raw is None:
            return api.SensorPir()
        return raw

    async def async_press(self) -> None:
        await self.runtime.client.reset_pir_time(self._index)
        await self.runtime.coordinator.async_request_refresh()
