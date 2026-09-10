"""Climate platform for Dingz."""

import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import api
from .conversions import dingz_to_hvac_action, dingz_to_hvac_mode, optional_float
from .coordinator import DingzConfigEntry, DingzCoordinator
from .entity import DelayedCoordinatorRefreshMixin, DingzEntity, entity_unique_id

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data
    entities: list[ClimateEntity] = []

    try:
        thermostat_enabled = runtime.coordinator.data["thermostat"]["active"]
    except LookupError:
        thermostat_enabled = False

    if thermostat_enabled:
        entities.append(Climate(runtime.coordinator))

    async_add_entities(entities)


class Climate(DingzEntity, ClimateEntity, DelayedCoordinatorRefreshMixin):
    def __init__(self, coordinator: DingzCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entity_unique_id(coordinator.runtime, "climate")
        self._attr_name = None
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_target_temperature_step = 1.0
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    @property
    def current_temperature(self) -> float | None:
        try:
            return optional_float(self.coordinator.data["thermostat"]["temp"])
        except LookupError:
            return None

    @property
    def target_temperature(self) -> float | None:
        try:
            return optional_float(self.coordinator.data["thermostat"]["target_temp"])
        except LookupError:
            return None

    @property
    def max_temp(self) -> float:
        try:
            value = optional_float(
                self.coordinator.data["thermostat"]["max_target_temp"]
            )
        except LookupError:
            value = None
        return 120 if value is None else value

    @property
    def min_temp(self) -> float:
        try:
            value = optional_float(
                self.coordinator.data["thermostat"]["min_target_temp"]
            )
        except LookupError:
            value = None
        return -55 if value is None else value

    @property
    def hvac_mode(self) -> HVACMode | None:
        try:
            raw = self.coordinator.data["thermostat"]["mode"]
        except LookupError:
            return None
        mode = dingz_to_hvac_mode(raw)
        if mode is None:
            _LOGGER.warning("invalid HVAC mode: %r", raw)
        return mode

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT]

    @property
    def hvac_action(self) -> HVACAction | None:
        try:
            raw = self.coordinator.data["thermostat"]["state"]
        except LookupError:
            return None
        action = dingz_to_hvac_action(raw)
        if action is None:
            _LOGGER.warning("invalid HVAC action: %r", raw)
        return action

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.runtime.client.update_thermostat_config(
            api.ThermostatConfig(
                enable=hvac_mode != HVACMode.OFF,
                free_cooling=hvac_mode != HVACMode.OFF,
                cooling=hvac_mode == HVACMode.COOL,
            )
        )
        await self.delayed_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        config = api.ThermostatConfig()
        if value := kwargs.get(ATTR_TEMPERATURE):
            config["target_temp"] = value
        if not config:
            return
        await self.runtime.client.update_thermostat_config(config)
        await self.delayed_request_refresh()
