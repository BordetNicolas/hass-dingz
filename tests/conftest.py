"""Shared pytest fixtures."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.fixtures.payloads import (
    full_device_config,
    ram_payload,
    state_payload,
    system_config,
)

try:
    import pytest_homeassistant_custom_component  # noqa: F401

    pytest_plugins = ["pytest_homeassistant_custom_component"]
    HAS_HA_PLUGIN = True
except ImportError:
    pytest_plugins = []
    HAS_HA_PLUGIN = False


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request: pytest.FixtureRequest) -> Generator[None]:
    if HAS_HA_PLUGIN:
        request.getfixturevalue("enable_custom_integrations")
    yield


@pytest.fixture
def mock_dingz_client() -> Generator[MagicMock]:
    """Patch the Dingz REST client used by the config flow and runtime."""
    with (
        patch("custom_components.dingz.api.Client", autospec=True) as client_cls,
        patch(
            "custom_components.dingz.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.dingz.coordinator.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        client = client_cls.return_value
        client.get_system_config = AsyncMock(return_value=system_config())
        client.get_info = AsyncMock(return_value={"mac": "246F28AABBCC"})
        client.get_state = AsyncMock(return_value=state_payload())
        client.get_full_device_config = AsyncMock(return_value=full_device_config())
        client.get_ram = AsyncMock(return_value=ram_payload())
        client.set_dimmer = AsyncMock()
        client.set_led = AsyncMock()
        client.move_blind = AsyncMock()
        client.move_blind_position = AsyncMock()
        client.set_ddi_channel = AsyncMock()
        client.update_mqtt_service_config = AsyncMock()
        client.update_thermostat_config = AsyncMock()
        client.set_temp_offset = AsyncMock()
        client.reset_pir_time = AsyncMock()
        client.save_default_config = AsyncMock()
        client.reboot = AsyncMock()
        client.base_url = "http://192.168.2.42"
        yield client


@pytest.fixture
def mock_mqtt_disabled() -> Generator[None]:
    with patch(
        "custom_components.dingz.mqtt.mqtt.mqtt_config_entry_enabled",
        return_value=False,
    ):
        yield
