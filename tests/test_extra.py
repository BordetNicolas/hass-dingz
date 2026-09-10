"""Climate, fan, button, number and text entity tests."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.button import ButtonEntityDescription
from homeassistant.components.text import TextEntityDescription

from custom_components.dingz.button import Action
from custom_components.dingz.climate import Climate
from custom_components.dingz.fan import Fan
from custom_components.dingz.number import TemperatureOffset
from custom_components.dingz.text import MqttJsonPath
from tests.fixtures.payloads import DINGZ_ID, full_device_config, state_payload


def _runtime(*, fan: bool = False) -> MagicMock:
    runtime = MagicMock()
    runtime.dingz_id = DINGZ_ID
    runtime.device_info = {}
    runtime.client = MagicMock()
    runtime.client.update_thermostat_config = AsyncMock()
    runtime.client.set_dimmer = AsyncMock()
    runtime.client.set_temp_offset = AsyncMock()
    runtime.client.update_mqtt_service_config = AsyncMock()
    runtime.client.reboot = AsyncMock()
    coordinator = MagicMock()
    coordinator.data = state_payload()
    coordinator.device_config = full_device_config(fan=fan)
    coordinator.runtime = runtime
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_refresh_config = AsyncMock()
    runtime.coordinator = coordinator
    return runtime


def test_climate_unique_id_and_temperature() -> None:
    runtime = _runtime()
    entity = Climate(runtime.coordinator)
    assert entity.unique_id == f"{DINGZ_ID}_climate"
    assert entity.current_temperature == 21.5
    assert entity.target_temperature == 21.0


def test_climate_false_temperature_is_none() -> None:
    runtime = _runtime()
    runtime.coordinator.data["thermostat"]["temp"] = False
    runtime.coordinator.data["thermostat"]["target_temp"] = False
    entity = Climate(runtime.coordinator)
    assert entity.current_temperature is None
    assert entity.target_temperature is None


def test_fan_unique_id() -> None:
    runtime = _runtime(fan=True)
    entity = Fan(runtime.coordinator, index=2)
    assert entity.unique_id == f"{DINGZ_ID}_fan_2"
    assert entity.is_on is False


async def test_number_temp_offset() -> None:
    runtime = _runtime()
    entity = TemperatureOffset(runtime.coordinator)
    assert entity.unique_id == f"{DINGZ_ID}_temp_offset"
    assert entity.native_value == 0.0
    await entity.async_set_native_value(1.6)
    runtime.client.set_temp_offset.assert_awaited_with(1.6)


async def test_text_mqtt_uri() -> None:
    runtime = _runtime()
    entity = MqttJsonPath(
        runtime.coordinator,
        TextEntityDescription(key="uri", translation_key="mqtt_uri"),
    )
    assert entity.unique_id == f"{DINGZ_ID}_mqtt_uri"
    assert entity.native_value == ""


async def test_button_reboot() -> None:
    runtime = _runtime()
    entity = Action(
        runtime,
        ButtonEntityDescription(key="reboot", translation_key="reboot"),
    )
    assert entity.unique_id == f"{DINGZ_ID}_reboot"
    await entity.async_press()
    runtime.client.reboot.assert_awaited_once()


async def test_climate_set_temperature() -> None:
    runtime = _runtime()
    entity = Climate(runtime.coordinator)
    with patch("custom_components.dingz.entity.COMMAND_REFRESH_DELAY", 0):
        await entity.async_set_temperature(temperature=22)
    runtime.client.update_thermostat_config.assert_awaited()
