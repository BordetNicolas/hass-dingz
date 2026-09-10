"""Switch platform for Dingz."""

from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import api
from .coordinator import DingzConfigEntry, DingzCoordinator, DingzRuntime
from .entity import (
    DelayedCoordinatorRefreshMixin,
    DingzEntity,
    UserAssignedNameMixin,
    compile_json_path,
    entity_unique_id,
    json_path_lookup,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data
    entities: list[SwitchEntity] = [
        MqttEnable(runtime.coordinator),
    ]

    for index, dingz_output in enumerate(runtime.device_config.outputs):
        if (
            dingz_output.get("active", False)
            and dingz_output.get("type") == "power_socket"
        ):
            entities.append(PowerSocket(runtime, index))

    async_add_entities(entities)


class MqttEnable(DingzEntity, SwitchEntity):
    def __init__(self, coordinator: DingzCoordinator) -> None:
        super().__init__(coordinator)
        desc = SwitchEntityDescription(
            key="enable",
            entity_category=EntityCategory.CONFIG,
            device_class=SwitchDeviceClass.SWITCH,
            translation_key="mqtt_enable",
        )
        self._attr_unique_id = entity_unique_id(coordinator.runtime, "mqtt_enable")
        self.entity_description = desc
        self._path = ["mqtt", *compile_json_path(desc.key)]

    @property
    def is_on(self) -> bool | None:
        return json_path_lookup(self.coordinator.device_config.services, self._path)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, value: bool) -> None:
        config = self.coordinator.device_config.services.get(
            "mqtt", api.ServicesConfigMqtt()
        )
        config[self.entity_description.key] = value
        await self.runtime.client.update_mqtt_service_config(config)
        await self.coordinator.async_refresh_config()
        self.async_write_ha_state()


class PowerSocket(
    DingzEntity,
    SwitchEntity,
    UserAssignedNameMixin,
    DelayedCoordinatorRefreshMixin,
):
    _attr_translation_key = "power_socket"

    def __init__(self, runtime: DingzRuntime, index: int) -> None:
        super().__init__(runtime.coordinator)
        self._index = index
        self._attr_unique_id = entity_unique_id(runtime, f"socket_{index}")

    @property
    def dingz_output_config(self) -> api.OutputConfig:
        try:
            return self.coordinator.device_config.outputs[self._index]
        except LookupError:
            return api.OutputConfig()

    @property
    def dingz_dimmer_state(self) -> api.StateDimmer:
        try:
            return self.coordinator.data["dimmers"][self._index]
        except LookupError:
            return api.StateDimmer()

    @property
    def comp_index(self) -> int:
        return self._index

    @property
    def user_given_name(self) -> str | None:
        return self.dingz_output_config.get("name")

    @property
    def is_on(self) -> bool | None:
        return self.dingz_dimmer_state.get("on")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.runtime.client.set_dimmer(self._index, "on")
        await self.delayed_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.runtime.client.set_dimmer(self._index, "off")
        await self.delayed_request_refresh()
