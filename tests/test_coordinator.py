"""Coordinator update, failure and recovery tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.dingz import api
from custom_components.dingz.coordinator import DingzCoordinator
from tests.fixtures.payloads import full_device_config, state_payload


def _coordinator(client: MagicMock) -> DingzCoordinator:
    runtime = MagicMock()
    runtime.hass = MagicMock()
    runtime.entry = MagicMock()
    runtime.client = client
    runtime.dingz_id = "abcd1234ef"
    with patch(
        "custom_components.dingz.coordinator.DataUpdateCoordinator.__init__",
        return_value=None,
    ):
        coordinator = DingzCoordinator(runtime)
    return coordinator


async def test_update_fetches_state() -> None:
    client = MagicMock()
    client.get_state = AsyncMock(return_value=state_payload())
    coordinator = _coordinator(client)
    data = await coordinator._async_update_data()
    assert data["sensors"]["brightness"] == 123
    client.get_state.assert_awaited_once()


async def test_update_timeout_becomes_update_failed() -> None:
    client = MagicMock()
    client.get_state = AsyncMock(side_effect=TimeoutError)
    coordinator = _coordinator(client)
    with pytest.raises(UpdateFailed, match="Timeout"):
        await coordinator._async_update_data()


async def test_update_client_error_becomes_update_failed() -> None:
    client = MagicMock()
    client.get_state = AsyncMock(side_effect=aiohttp.ClientConnectionError("down"))
    coordinator = _coordinator(client)
    with pytest.raises(UpdateFailed, match="Error communicating"):
        await coordinator._async_update_data()


async def test_update_ram_error_becomes_update_failed() -> None:
    client = MagicMock()
    client.get_state = AsyncMock(side_effect=api.NotEnoughRamError("oom"))
    coordinator = _coordinator(client)
    with pytest.raises(UpdateFailed, match="oom"):
        await coordinator._async_update_data()


async def test_config_reloads_when_timestamp_changes() -> None:
    client = MagicMock()
    first = state_payload()
    second = state_payload()
    second["config"] = {"timestamp": 1700000999}
    client.get_state = AsyncMock(side_effect=[first, second])
    client.get_full_device_config = AsyncMock(return_value=full_device_config())
    coordinator = _coordinator(client)

    await coordinator._async_update_data()
    client.get_full_device_config.assert_not_called()

    await coordinator._async_update_data()
    client.get_full_device_config.assert_awaited_once()


async def test_recovery_after_failure() -> None:
    client = MagicMock()
    client.get_state = AsyncMock(
        side_effect=[aiohttp.ClientConnectionError("down"), state_payload()]
    )
    coordinator = _coordinator(client)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    data = await coordinator._async_update_data()
    assert data["led"]["on"] is True
