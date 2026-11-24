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

from . import api, capabilities
from .coordinator import DingzConfigEntry, DingzCoordinator, DingzRuntime
from .entity import (
    DelayedCoordinatorRefreshMixin,
    DingzEntity,
    DingzOutputEntity,
    async_command,
    compile_json_path,
    entity_unique_id,
    json_path_lookup,
    output_slots,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data
    entities: list[SwitchEntity] = [
        MqttEnable(runtime.coordinator),
    ]

    for slot in output_slots(runtime, "power_socket"):
        entities.append(PowerSocket(runtime, slot))

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
        config = api.ServicesConfigMqtt(
            **self.coordinator.device_config.services.get("mqtt", {})
        )
        config["enable"] = value
        await async_command(self.runtime.client.update_mqtt_service_config(config))
        await async_command(self.coordinator.async_refresh_config())
        self.async_write_ha_state()


class PowerSocket(
    DingzOutputEntity,
    SwitchEntity,
    DelayedCoordinatorRefreshMixin,
):
    _attr_translation_key = "power_socket"
    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(self, runtime: DingzRuntime, slot: capabilities.Slot) -> None:
        super().__init__(runtime.coordinator, slot=slot)
        self._attr_unique_id = entity_unique_id(runtime, f"socket_{slot.absolute}")

    @property
    def is_on(self) -> bool | None:
        return self.dingz_dimmer.get("on")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await async_command(self.runtime.client.set_dimmer(self._slot.relative, "on"))
        await self.delayed_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await async_command(self.runtime.client.set_dimmer(self._slot.relative, "off"))
        await self.delayed_request_refresh()
