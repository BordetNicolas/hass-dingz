"""Light, switch and cover entity behaviour."""

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.dingz.cover import Blind
from custom_components.dingz.light import Dimmer, FrontLed
from custom_components.dingz.switch import PowerSocket
from tests.fixtures.payloads import DINGZ_ID, full_device_config, state_payload


def _runtime() -> MagicMock:
    runtime = MagicMock()
    runtime.dingz_id = DINGZ_ID
    runtime.device_info = {}
    runtime.client = MagicMock()
    runtime.client.set_dimmer = AsyncMock()
    runtime.client.set_led = AsyncMock()
    runtime.client.move_blind = AsyncMock()
    runtime.client.move_blind_position = AsyncMock()
    coordinator = MagicMock()
    coordinator.data = state_payload()
    coordinator.device_config = full_device_config()
    coordinator.runtime = runtime
    coordinator.async_request_refresh = AsyncMock()
    runtime.coordinator = coordinator
    return runtime


async def test_dimmer_state_and_turn_on() -> None:
    runtime = _runtime()
    entity = Dimmer(runtime, 0)
    entity.handle_state_update()
    assert entity.is_on is True
    assert entity.brightness == 204
    assert entity.unique_id == f"{DINGZ_ID}_output_0"

    with patch("custom_components.dingz.entity.COMMAND_REFRESH_DELAY", 0):
        await entity.async_turn_on(brightness=255)
    runtime.client.set_dimmer.assert_awaited()
    args = runtime.client.set_dimmer.await_args
    assert args.args[0] == 0
    assert args.args[1] == "on"
    assert args.kwargs["value"] == 100


async def test_dimmer_turn_off() -> None:
    runtime = _runtime()
    entity = Dimmer(runtime, 0)
    with patch("custom_components.dingz.entity.COMMAND_REFRESH_DELAY", 0):
        await entity.async_turn_off()
    runtime.client.set_dimmer.assert_awaited_with(0, "off", time=None)


async def test_switch_on_off() -> None:
    runtime = _runtime()
    entity = PowerSocket(runtime, 2)
    assert entity.is_on is False
    assert entity.unique_id == f"{DINGZ_ID}_socket_2"
    with patch("custom_components.dingz.entity.COMMAND_REFRESH_DELAY", 0):
        await entity.async_turn_on()
        await entity.async_turn_off()
    assert runtime.client.set_dimmer.await_count == 2


async def test_front_led() -> None:
    runtime = _runtime()
    entity = FrontLed(runtime.coordinator)
    assert entity.is_on is True
    assert entity.hs_color == (120, 50)
    await entity.async_turn_off()
    runtime.client.set_led.assert_awaited()


async def test_cover_positions_and_commands() -> None:
    runtime = _runtime()
    entity = Blind(runtime, index=0)
    entity.handle_state_update()
    assert entity.current_cover_position == 40
    assert entity.current_cover_tilt_position == 20
    assert entity.is_closed is False
    assert entity.unique_id == f"{DINGZ_ID}_cover_0"

    with patch("custom_components.dingz.entity.COMMAND_REFRESH_DELAY", 0):
        await entity.async_open_cover()
        await entity.async_close_cover()
        await entity.async_stop_cover()
        await entity.async_set_cover_position(position=70)
    runtime.client.move_blind.assert_any_await(0, "up")
    runtime.client.move_blind.assert_any_await(0, "down")
    runtime.client.move_blind.assert_any_await(0, "stop")
    runtime.client.move_blind_position.assert_awaited()
