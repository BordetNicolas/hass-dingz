"""Tests for the Dingz REST client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from yarl import URL

from custom_components.dingz import api
from tests.fixtures.payloads import state_payload, system_config


def _session_get(payload: object, status: int = 200) -> MagicMock:
    session = MagicMock()
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=payload)
    if status >= 400:
        resp.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=status,
            message="error",
        )
    else:
        resp.raise_for_status = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=resp)
    session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    return session


async def test_get_state() -> None:
    payload = state_payload()
    client = api.Client(_session_get(payload), URL("http://192.168.2.42"))
    assert await client.get_state() == payload


async def test_get_system_config() -> None:
    payload = system_config()
    client = api.Client(_session_get(payload), URL("http://192.168.2.42"))
    assert await client.get_system_config() == payload


async def test_get_retries_client_error_then_raises() -> None:
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(
        side_effect=aiohttp.ClientConnectionError("down")
    )
    session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    client = api.Client(session, "http://192.168.2.42")
    client._lock.throttle_duration = 0
    with pytest.raises(aiohttp.ClientConnectionError):
        await client._get("state", attempts=2, retry_delay=0)


async def test_services_config_payload_is_redacted() -> None:
    assert api._payload_for_log(
        "services_config", {"mqtt": {"uri": "mqtt://u:p@h"}}
    ) == ("<redacted>")
    assert api._payload_for_log("dimmer/0/on", {"value": 50}) == {"value": 50}


def _session_post(statuses: list[int]) -> MagicMock:
    session = MagicMock()
    responses = []
    for status in statuses:
        resp = MagicMock()
        resp.status = status
        if status >= 400:
            resp.raise_for_status.side_effect = aiohttp.ClientResponseError(
                request_info=MagicMock(), history=(), status=status, message="err"
            )
        responses.append(resp)
    session.post.return_value.__aenter__ = AsyncMock(side_effect=responses)
    session.post.return_value.__aexit__ = AsyncMock(return_value=None)
    return session


def _fast(client: api.Client) -> api.Client:
    client._lock.throttle_duration = 0
    return client


async def test_post_does_not_retry_client_errors() -> None:
    session = _session_post([400, 200])
    client = _fast(api.Client(session, "http://192.168.2.42"))
    with pytest.raises(aiohttp.ClientResponseError):
        await client._post("dimmer/0/on", {}, retry_delay=0)
    assert session.post.call_count == 1


async def test_post_retries_server_errors() -> None:
    session = _session_post([503, 200])
    client = _fast(api.Client(session, "http://192.168.2.42"))
    await client._post("dimmer/0/on", {}, retry_delay=0)
    assert session.post.call_count == 2


async def test_reboot_is_never_repeated() -> None:
    session = MagicMock()
    session.post.return_value.__aenter__ = AsyncMock(side_effect=TimeoutError)
    session.post.return_value.__aexit__ = AsyncMock(return_value=None)
    client = _fast(api.Client(session, "http://192.168.2.42"))
    with pytest.raises(TimeoutError):
        await client.reboot()
    assert session.post.call_count == 1


async def test_thermostat_commands() -> None:
    client = api.Client(MagicMock(), "http://192.168.2.42")
    client._post = AsyncMock()
    await client.set_thermostat(target_temp=21.5, enable=False)
    client._post.assert_awaited_with(
        "thermostat", {"target_temp": 21.5, "enable": "false"}, as_query_params=True
    )
    await client.set_thermostat_mode("cooling")
    client._post.assert_awaited_with("thermostat/mode/cooling", {})


async def test_command_urls_and_params() -> None:
    client = api.Client(MagicMock(), "http://192.168.2.42")
    client._post = AsyncMock()
    await client.set_dimmer(1, "on", value=50, time=0.5)
    client._post.assert_awaited_with(
        "dimmer/1/on", {"value": 50, "time": 0.5}, as_query_params=True
    )
    await client.move_blind_position(0, blind=10, lamella=20)
    client._post.assert_awaited_with(
        "shade/0", {"blind": 10, "lamella": 20}, as_query_params=True
    )
    await client.set_led(api.SetLedState(action="on", color="1;2;3", mode="hsv"))
    client._post.assert_awaited_with("led/set", "action=on&color=1;2;3&mode=hsv")


async def test_server_error_checks_ram() -> None:
    client = _fast(api.Client(_session_get({}, status=500), "http://192.168.2.42"))
    client.get_ram = AsyncMock(return_value={"free": 100, "largest_free_block": 10})
    with pytest.raises(api.NotEnoughRamError):
        await client._get("state", attempts=1, retry_delay=0)


async def test_ddi_channels_missing_returns_empty() -> None:
    client = _fast(api.Client(_session_get(None, status=404), "http://192.168.2.42"))
    assert await client.get_ddi_channels_config() == []


async def test_throttle_waits_between_requests() -> None:
    lock = api._ReqThrottleLock(0.05)
    async with lock:
        pass
    loop = asyncio.get_running_loop()
    start = loop.time()
    async with lock:
        pass
    assert loop.time() - start >= 0.04


async def test_full_device_config_from_captured_device() -> None:
    from tests.fixtures import devices

    raw = devices.load("fw260_dip0_two_blinds")
    responses = {
        "device": raw["device"],
        "system_config": raw["system_config"],
        "services_config": raw["services_config"],
        "button_config": raw["button_config"],
        "ddi_channels_config": raw["ddi_channels_config"],
        "input_config": raw["input_config"],
        "output_config": raw["output_config"],
        "blind_config": raw["blind_config"],
    }
    client = api.Client(MagicMock(), "http://192.0.2.10")
    client._get = AsyncMock(side_effect=lambda path, **_: responses.get(path, {}))
    client._post = AsyncMock()
    config = await client.get_full_device_config()
    assert config == devices.full_config(raw)
    for getter in ("get_state", "get_device", "get_info", "get_ram"):
        await getattr(client, getter)()
    await client.update_mqtt_service_config({"enable": True})
    await client.set_temp_offset(1.5)
    await client.move_blind(0, "stop")
    await client.reset_pir_time(1)
    await client.save_default_config()
    await client.set_ddi_channel(0, "on", brightness=10, color_temperature=3000)
