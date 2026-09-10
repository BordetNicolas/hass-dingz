"""Sensor platform for Dingz."""

import contextlib
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfInformation,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .coordinator import DingzConfigEntry, DingzCoordinator, DingzRuntime
from .entity import (
    CoordinatedNotificationStateEntity,
    DiagnosticEntity,
    DingzEntity,
    DingzOutputEntity,
    compile_json_path,
    entity_unique_id,
    json_path_lookup,
)
from .models import InternalNotification, SimpleSensorStateNotification


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data

    entities: list[SensorEntity] = [
        Brightness(runtime),
        JsonPathSensor(
            runtime.coordinator,
            SensorEntityDescription(
                key="sensors.light_state",
                device_class=SensorDeviceClass.ENUM,
                options=["day", "night", "twilight"],
                translation_key="light_state",
            ),
        ),
        JsonPathSensor(
            runtime.coordinator,
            SensorEntityDescription(
                key="time",
                device_class=SensorDeviceClass.TIMESTAMP,
                translation_key="state_time",
                entity_category=EntityCategory.DIAGNOSTIC,
                entity_registry_enabled_default=False,
            ),
            transform_fn=_dt_with_hass_tz,
        ),
        JsonPathSensor(
            runtime.coordinator,
            SensorEntityDescription(
                key="config.timestamp",
                device_class=SensorDeviceClass.TIMESTAMP,
                translation_key="config_timestamp",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            transform_fn=lambda raw: dt_util.utc_from_timestamp(raw),
        ),
        DiagnosticJsonPathSensor(
            runtime.diagnostic,
            SensorEntityDescription(
                key="free",
                state_class=SensorStateClass.MEASUREMENT,
                device_class=SensorDeviceClass.DATA_SIZE,
                native_unit_of_measurement=UnitOfInformation.BYTES,
                translation_key="diag_free",
                entity_category=EntityCategory.DIAGNOSTIC,
                entity_registry_enabled_default=False,
            ),
        ),
        DiagnosticJsonPathSensor(
            runtime.diagnostic,
            SensorEntityDescription(
                key="largest_free_block",
                state_class=SensorStateClass.MEASUREMENT,
                device_class=SensorDeviceClass.DATA_SIZE,
                native_unit_of_measurement=UnitOfInformation.BYTES,
                translation_key="diag_largest_free_block",
                entity_category=EntityCategory.DIAGNOSTIC,
                entity_registry_enabled_default=False,
            ),
        ),
    ]

    try:
        dyn_light_enabled = runtime.device_config.system["dyn_light"]["enable"]
    except LookupError:
        dyn_light_enabled = False

    if dyn_light_enabled:
        entities.append(
            JsonPathSensor(
                runtime.coordinator,
                SensorEntityDescription(
                    key="dyn_light.mode",
                    device_class=SensorDeviceClass.ENUM,
                    options=["day", "night", "twilight"],
                    translation_key="dyn_light",
                ),
            )
        )

    for name, is_diag in (
        ("room_temperature", False),
        ("uncompensated_temperature", True),
        ("cpu_temperature", True),
        ("puck_temperature", True),
        ("fet_temperature", True),
    ):
        entities.append(
            JsonPathSensor(
                runtime.coordinator,
                SensorEntityDescription(
                    key=f"sensors.{name}",
                    device_class=SensorDeviceClass.TEMPERATURE,
                    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                    state_class=SensorStateClass.MEASUREMENT,
                    entity_category=EntityCategory.DIAGNOSTIC if is_diag else None,
                    translation_key=name,
                ),
            )
        )

    for index, dingz_output in enumerate(runtime.device_config.outputs):
        if dingz_output.get("active", False):
            entities.append(OutputPower(runtime.coordinator, index=index))

    async_add_entities(entities)


def _dt_with_hass_tz(s: str) -> datetime | None:
    parsed = dt_util.parse_datetime(s)
    if parsed is None:
        return None
    return dt_util.as_utc(parsed)


class OutputPower(DingzOutputEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "output_power"

    def __init__(self, coordinator: DingzCoordinator, *, index: int) -> None:
        super().__init__(coordinator, index=index)
        self._attr_unique_id = entity_unique_id(
            coordinator.runtime, f"output_power_{index}"
        )

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        try:
            power_outputs = self.coordinator.data["sensors"]["power_outputs"]
            power_output = power_outputs[self.comp_index]
        except LookupError:
            return None
        return power_output.get("value")


class JsonPathSensor(DingzEntity, SensorEntity):
    def __init__(
        self,
        coordinator: DingzCoordinator,
        desc: SensorEntityDescription,
        *,
        transform_fn: Callable[[Any], StateType | date | datetime | Decimal]
        | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entity_unique_id(coordinator.runtime, desc.key)
        self.entity_description = desc
        self._path = compile_json_path(desc.key)
        self._transform_fn = transform_fn

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        value = json_path_lookup(self.coordinator.data, self._path)
        if value is None:
            return None
        if self._transform_fn:
            return self._transform_fn(value)
        return value


class DiagnosticJsonPathSensor(DiagnosticEntity, SensorEntity):
    def __init__(
        self,
        coordinator,
        desc: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entity_unique_id(coordinator.runtime, f"diag_{desc.key}")
        self.entity_description = desc
        self._path = compile_json_path(desc.key)

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        return json_path_lookup(self.coordinator.data, self._path)


class Brightness(CoordinatedNotificationStateEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "lx"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "brightness"

    def __init__(self, runtime: DingzRuntime) -> None:
        super().__init__(runtime)
        self._brightness: float | None = None
        self._attr_unique_id = entity_unique_id(runtime, "brightness")
        self._attr_device_info = runtime.device_info

    @callback
    def handle_notification(self, notification: InternalNotification) -> None:
        if not (
            isinstance(notification, SimpleSensorStateNotification)
            and notification.sensor == "light"
        ):
            return
        self._brightness = notification.value
        self.async_write_ha_state()

    @callback
    def handle_state_update(self) -> None:
        with contextlib.suppress(LookupError):
            self._brightness = self.coordinator.data["sensors"]["brightness"]

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        return self._brightness
