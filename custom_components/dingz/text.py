"""Text platform for Dingz."""

from typing import Any, cast

from homeassistant.components.text import TextEntity, TextEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from yarl import URL

from . import api
from .coordinator import DingzConfigEntry, DingzCoordinator
from .entity import (
    DingzEntity,
    async_command,
    entity_unique_id,
    json_path_lookup,
)

PARALLEL_UPDATES = 0

MASK = "********"


def mask_uri_password(value: str) -> str:
    """Hide the broker password: entity states end up in the recorder."""
    try:
        url = URL(value)
    except ValueError:
        return value
    if url.password is None:
        return value
    return str(url.with_password(MASK))


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
                mask_password=True,
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
    _attr_native_max = 255

    def __init__(
        self,
        coordinator: DingzCoordinator,
        desc: TextEntityDescription,
        *,
        none_if_empty: bool = False,
        mask_password: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entity_unique_id(
            coordinator.runtime, f"mqtt_{desc.key.replace('.', '_')}"
        )
        self.entity_description = desc
        # Keys are literal: "server.crt" contains a dot but is a single key.
        self._path: list[str | int] = ["mqtt", desc.key]
        self._none_if_empty = none_if_empty
        self._mask_password = mask_password

    @property
    def native_value(self) -> str | None:
        value = json_path_lookup(self.coordinator.device_config.services, self._path)
        if value is None and self._none_if_empty:
            value = ""
        if self._mask_password and isinstance(value, str):
            value = mask_uri_password(value)
        if isinstance(value, str) and len(value) > self.native_max:
            # A PEM certificate does not fit in a Home Assistant state.
            return None
        return value

    async def async_set_value(self, value: str | None) -> None:
        value = value.strip() if value else None
        if self._none_if_empty and value == "":
            value = None

        current = self.coordinator.device_config.services.get("mqtt", {})
        if (
            self._mask_password
            and value is not None
            and (password := _password(current.get("uri")))
            and _password(value) == MASK
        ):
            # The user edited the masked value: keep the stored password.
            value = str(URL(value).with_password(password))

        config = dict(current)
        config[self.entity_description.key] = value
        await async_command(
            self.runtime.client.update_mqtt_service_config(
                cast(api.ServicesConfigMqtt, config)
            )
        )
        await async_command(self.coordinator.async_refresh_config())


def _password(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return URL(value).password
    except ValueError:
        return None
