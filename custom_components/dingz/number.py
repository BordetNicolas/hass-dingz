"""Number platform for Dingz."""

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DingzConfigEntry, DingzCoordinator
from .entity import DingzEntity, entity_unique_id


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data
    async_add_entities([TemperatureOffset(runtime.coordinator)])


class TemperatureOffset(DingzEntity, NumberEntity):
    def __init__(self, coordinator: DingzCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entity_unique_id(coordinator.runtime, "temp_offset")
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_translation_key = "temperature_offset"
        self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_native_step = 0.5
        self._attr_native_min_value = -30
        self._attr_native_max_value = 30

    @property
    def native_value(self) -> float | None:
        try:
            return self.coordinator.device_config.system["temp_offset"]
        except LookupError:
            return None

    async def async_set_native_value(self, value: float) -> None:
        value = round(value, 1)
        await self.runtime.client.set_temp_offset(value)
        await self.coordinator.async_refresh_config()
        await self.coordinator.async_request_refresh()
