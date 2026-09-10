"""Light platform for Dingz."""

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_TRANSITION,
    LightEntity,
)
from homeassistant.components.light.const import ColorMode, LightEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import api
from .conversions import (
    brightness_dingz_to_ha,
    brightness_ha_to_dingz,
    hsv_to_led_color,
    parse_hsv,
    transition_to_ramp_ms,
)
from .coordinator import DingzConfigEntry, DingzCoordinator, DingzRuntime
from .entity import (
    CoordinatedNotificationStateEntity,
    DelayedCoordinatorRefreshMixin,
    UserAssignedNameMixin,
    entity_unique_id,
)
from .models import InternalNotification, LightStateNotification


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DingzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = config_entry.runtime_data
    entities: list[LightEntity] = [FrontLed(runtime.coordinator)]

    for index, dingz_output in enumerate(runtime.device_config.outputs):
        if dingz_output.get("active", False) and dingz_output.get("type") == "light":
            entities.append(Dimmer(runtime, index))
    if runtime.device_config.device.get("ddi_base", False):
        for index, ddi in enumerate(runtime.device_config.ddi_channels):
            if ddi.get("en", False):
                entities.append(Ddi(runtime, index))

    async_add_entities(entities)


class FrontLed(CoordinatorEntity[DingzCoordinator], LightEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "front"
    _attr_color_mode = ColorMode.HS
    _attr_supported_color_modes = {ColorMode.HS}
    _attr_supported_features = LightEntityFeature.TRANSITION

    def __init__(self, coordinator: DingzCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entity_unique_id(coordinator.runtime, "front_led")
        self._attr_device_info = coordinator.runtime.device_info

    @property
    def dingz_hsv_tuple(self) -> tuple[int, int, int] | None:
        try:
            raw = self.coordinator.data["led"]["hsv"]
        except LookupError:
            return None
        return parse_hsv(raw)

    @property
    def brightness(self) -> int | None:
        hsv = self.dingz_hsv_tuple
        if hsv is None:
            return None
        return brightness_dingz_to_ha(hsv[2])

    @property
    def hs_color(self) -> tuple[float, float] | None:
        hsv = self.dingz_hsv_tuple
        if hsv is None:
            return None
        return hsv[0:2]

    @property
    def is_on(self) -> bool | None:
        try:
            return self.coordinator.data["led"]["on"]
        except LookupError:
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS, self.brightness)
        if brightness is None:
            brightness = 255

        hs = kwargs.get(ATTR_HS_COLOR, self.hs_color)
        if hs is None:
            h, s = (0.0, 100.0)
        else:
            h, s = hs

        await self.coordinator.runtime.client.set_led(
            api.SetLedState(
                action="on",
                color=hsv_to_led_color(h, s, brightness),
                mode="hsv",
                ramp=transition_to_ramp_ms(kwargs.get(ATTR_TRANSITION)),
            )
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.runtime.client.set_led(
            api.SetLedState(
                action="off",
                ramp=transition_to_ramp_ms(kwargs.get(ATTR_TRANSITION)),
            )
        )
        await self.coordinator.async_request_refresh()


class Dimmer(
    CoordinatedNotificationStateEntity,
    LightEntity,
    UserAssignedNameMixin,
    DelayedCoordinatorRefreshMixin,
):
    _attr_supported_features = LightEntityFeature.TRANSITION
    _attr_translation_key = "dimmer"

    def __init__(self, runtime: DingzRuntime, index: int) -> None:
        super().__init__(runtime)
        self._index = index
        self._attr_unique_id = entity_unique_id(runtime, f"output_{index}")
        self._attr_device_info = runtime.device_info

    @property
    def dingz_output_config(self) -> api.OutputConfig:
        try:
            return self.coordinator.device_config.outputs[self._index]
        except LookupError:
            return api.OutputConfig()

    @property
    def dingz_dimmable(self) -> bool:
        try:
            return self.dingz_output_config["light"]["dimmable"]
        except LookupError:
            return False

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
    def color_mode(self) -> ColorMode | str | None:
        return ColorMode.BRIGHTNESS if self.dingz_dimmable else ColorMode.ONOFF

    @property
    def supported_color_modes(self) -> set[ColorMode] | set[str] | None:
        return {ColorMode.BRIGHTNESS} if self.dingz_dimmable else {ColorMode.ONOFF}

    @callback
    def handle_notification(self, notification: InternalNotification) -> None:
        if not (
            isinstance(notification, LightStateNotification)
            and notification.index == self._index
        ):
            return
        match notification.turn:
            case "on":
                self._attr_is_on = True
            case "off":
                self._attr_is_on = False
        self._attr_brightness = brightness_dingz_to_ha(notification.brightness)
        self.async_write_ha_state()

    @callback
    def handle_state_update(self) -> None:
        self._attr_is_on = self.dingz_dimmer_state.get("on")
        if (output := self.dingz_dimmer_state.get("output")) is not None:
            self._attr_brightness = brightness_dingz_to_ha(output)

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            brightness = kwargs[ATTR_BRIGHTNESS]
        except LookupError:
            value = None
        else:
            value = brightness_ha_to_dingz(brightness)

        await self.coordinator.runtime.client.set_dimmer(
            self._index, "on", value=value, time=kwargs.get(ATTR_TRANSITION)
        )
        await self.delayed_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.runtime.client.set_dimmer(
            self._index, "off", time=kwargs.get(ATTR_TRANSITION)
        )
        await self.delayed_request_refresh()


class Ddi(
    CoordinatedNotificationStateEntity,
    LightEntity,
    UserAssignedNameMixin,
    DelayedCoordinatorRefreshMixin,
):
    _attr_supported_features = LightEntityFeature.TRANSITION
    _attr_translation_key = "ddi"
    _attr_min_color_temp_kelvin = 2700
    _attr_max_color_temp_kelvin = 6500

    def __init__(self, runtime: DingzRuntime, index: int) -> None:
        super().__init__(runtime)
        self._index = index
        self._attr_unique_id = entity_unique_id(runtime, f"ddi_{index}")
        self._attr_device_info = runtime.device_info

    @property
    def dingz_ddi_channel_config(self) -> api.DdiChannelConfig:
        try:
            return self.coordinator.device_config.ddi_channels[self._index]
        except LookupError:
            return api.DdiChannelConfig()

    @property
    def dingz_ddi_channel_state(self) -> api.StateDdiChannel:
        try:
            return self.coordinator.data["ddi_channels"][self._index]
        except LookupError:
            return api.StateDdiChannel()

    @property
    def comp_index(self) -> int:
        return self._index

    @property
    def user_given_name(self) -> str | None:
        return self.dingz_ddi_channel_config.get("name")

    @property
    def color_mode(self) -> ColorMode:
        return (
            ColorMode.COLOR_TEMP
            if self.dingz_ddi_channel_state.get("ct_enabled", False)
            else ColorMode.BRIGHTNESS
        )

    @property
    def supported_color_modes(self) -> set[ColorMode] | set[str] | None:
        if self.dingz_ddi_channel_config.get("features", {}).get(
            "colour_temperature", {}
        ).get("en", False) or self.dingz_ddi_channel_state.get("ct_enabled", False):
            return {ColorMode.COLOR_TEMP}
        return {ColorMode.BRIGHTNESS}

    @callback
    def handle_notification(self, notification: InternalNotification) -> None:
        return

    @callback
    def handle_state_update(self) -> None:
        channel_state = self.dingz_ddi_channel_state
        self._attr_is_on = channel_state.get("on")
        if (output := channel_state.get("brightness")) is not None:
            self._attr_brightness = brightness_dingz_to_ha(output)
        if (temp := channel_state.get("colour_temperature_k")) is not None:
            self._attr_color_temp_kelvin = temp

    async def async_turn_on(self, **kwargs: Any) -> None:
        color_temperature = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        try:
            brightness = kwargs[ATTR_BRIGHTNESS]
        except LookupError:
            brightness = None
        else:
            brightness = brightness_ha_to_dingz(brightness)

        if brightness is None and color_temperature is not None:
            brightness = self.dingz_ddi_channel_state.get("brightness")

        await self.coordinator.runtime.client.set_ddi_channel(
            self._index,
            "on",
            brightness=brightness,
            color_temperature=color_temperature,
            time=kwargs.get(ATTR_TRANSITION),
        )
        await self.delayed_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.runtime.client.set_ddi_channel(
            self._index,
            "off",
            time=kwargs.get(ATTR_TRANSITION),
        )
        await self.delayed_request_refresh()
