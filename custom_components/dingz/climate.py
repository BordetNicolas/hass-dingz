"""Climate platform for Dingz."""

import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import api, capabilities
from .conversions import dingz_to_hvac_action, dingz_to_hvac_mode, optional_float
from .coordinator import DingzConfigEntry, DingzCoordinator
from .entity import (
    DelayedCoordinatorRefreshMixin,
    DingzEntity,
    async_command,
    entity_unique_id,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

# Home Assistant 2026.11 renamed the temperature members to ``native_*`` and
# deprecated the old names; older releases only know the old names.
_HAS_NATIVE_TEMPERATURES = hasattr(ClimateEntity, "native_current_temperature")
_HAS_NATIVE_UNIT = hasattr(ClimateEntity, "native_temperature_unit")

# Fallbacks matching the documented API range (-55..125 °C).
_DEFAULT_MIN_TEMP = -55.0
_DEFAULT_MAX_TEMP = 125.0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data
    entities: list[ClimateEntity] = []

    if capabilities.thermostat_active(runtime.coordinator.data or {}):
        entities.append(Climate(runtime.coordinator))

    async_add_entities(entities)


class Climate(DingzEntity, ClimateEntity, DelayedCoordinatorRefreshMixin):
    _attr_name = None
    _attr_target_temperature_step = 1.0
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    if _HAS_NATIVE_UNIT:
        _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    else:
        _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: DingzCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entity_unique_id(coordinator.runtime, "climate")

    @property
    def dingz_thermostat(self) -> api.StateThermostat:
        thermostat = (self.coordinator.data or {}).get("thermostat")
        return thermostat if isinstance(thermostat, dict) else api.StateThermostat()

    def _current_temperature(self) -> float | None:
        return optional_float(self.dingz_thermostat.get("temp"))

    def _target_temperature(self) -> float | None:
        return optional_float(self.dingz_thermostat.get("target_temp"))

    if _HAS_NATIVE_TEMPERATURES:

        @property
        def native_current_temperature(self) -> float | None:
            return self._current_temperature()

        @property
        def native_target_temperature(self) -> float | None:
            return self._target_temperature()

    else:

        @property
        def current_temperature(self) -> float | None:
            return self._current_temperature()

        @property
        def target_temperature(self) -> float | None:
            return self._target_temperature()

    @property
    def max_temp(self) -> float:
        value = optional_float(self.dingz_thermostat.get("max_target_temp"))
        return _DEFAULT_MAX_TEMP if value is None else value

    @property
    def min_temp(self) -> float:
        value = optional_float(self.dingz_thermostat.get("min_target_temp"))
        return _DEFAULT_MIN_TEMP if value is None else value

    @property
    def hvac_mode(self) -> HVACMode | None:
        thermostat = self.dingz_thermostat
        if thermostat.get("enabled") is False:
            return HVACMode.OFF
        raw = thermostat.get("mode")
        if raw is None:
            return None
        mode = dingz_to_hvac_mode(raw)
        if mode is None:
            _LOGGER.debug("unknown thermostat mode: %r", raw)
        return mode

    @property
    def hvac_action(self) -> HVACAction | None:
        raw = self.dingz_thermostat.get("state")
        if raw is None:
            return None
        action = dingz_to_hvac_action(raw)
        if action is None:
            _LOGGER.debug("unknown thermostat state: %r", raw)
        return action

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        client = self.runtime.client
        if hvac_mode == HVACMode.OFF:
            await async_command(client.set_thermostat(enable=False))
        else:
            await async_command(
                client.set_thermostat_mode(
                    "cooling" if hvac_mode == HVACMode.COOL else "heating"
                )
            )
            await async_command(client.set_thermostat(enable=True))
        await self.delayed_request_refresh()

    async def async_turn_on(self) -> None:
        await async_command(self.runtime.client.set_thermostat(enable=True))
        await self.delayed_request_refresh()

    async def async_turn_off(self) -> None:
        await async_command(self.runtime.client.set_thermostat(enable=False))
        await self.delayed_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self.async_set_hvac_mode(hvac_mode)
        if (value := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await async_command(self.runtime.client.set_thermostat(target_temp=value))
        await self.delayed_request_refresh()
