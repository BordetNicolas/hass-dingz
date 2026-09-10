"""Text platform for Dingz."""

from homeassistant.components.text import TextEntity, TextEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import api
from .coordinator import DingzConfigEntry, DingzCoordinator
from .entity import DingzEntity, compile_json_path, entity_unique_id, json_path_lookup


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data
    async_add_entities(
        [
            MqttJsonPath(
                runtime.coordinator,
                TextEntityDescription(
                    key="uri",
                    entity_category=EntityCategory.CONFIG,
                    translation_key="mqtt_uri",
                    pattern=r"^(?:mqtts?:\/\/(?:[^:\n]+:[^@\n]+@)?[^@:\n]+(?::\d+)?)?$",
                ),
            ),
            MqttJsonPath(
                runtime.coordinator,
                TextEntityDescription(
                    key="server.crt",
                    entity_category=EntityCategory.CONFIG,
                    translation_key="mqtt_server_crt",
                ),
                none_if_empty=True,
            ),
        ]
    )


class MqttJsonPath(DingzEntity, TextEntity):
    def __init__(
        self,
        coordinator: DingzCoordinator,
        desc: TextEntityDescription,
        *,
        none_if_empty: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entity_unique_id(
            coordinator.runtime, f"mqtt_{desc.key.replace('.', '_')}"
        )
        self.entity_description = desc
        self._path = ["mqtt", *compile_json_path(desc.key)]
        self._none_if_empty = none_if_empty

    @property
    def native_value(self) -> str | None:
        value = json_path_lookup(self.coordinator.device_config.services, self._path)
        if value is None and self._none_if_empty:
            value = ""
        return value

    async def async_set_value(self, value: str | None) -> None:
        value = value.strip() if value else None
        if self._none_if_empty and value == "":
            value = None

        config = self.coordinator.device_config.services.get(
            "mqtt", api.ServicesConfigMqtt()
        )
        config[self.entity_description.key] = value
        await self.runtime.client.update_mqtt_service_config(config)
        await self.coordinator.async_refresh_config()
