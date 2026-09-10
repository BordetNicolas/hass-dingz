"""Tests for the Dingz REST client."""

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
