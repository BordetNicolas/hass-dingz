"""Config flow tests."""

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from ipaddress import ip_address
from unittest.mock import AsyncMock

import aiohttp
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.dingz.const import CONF_BASE_URL, DOMAIN
from tests.fixtures.payloads import BASE_URL, DINGZ_HOST, DINGZ_ID, system_config
from tests.ha_helpers import MockConfigEntry


async def test_user_flow_success(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": DINGZ_HOST}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BASE_URL] == BASE_URL
    assert result["result"].unique_id == DINGZ_ID


async def test_user_flow_cannot_connect(hass: HomeAssistant, mock_dingz_client) -> None:
    mock_dingz_client.get_system_config = AsyncMock(
        side_effect=aiohttp.ClientConnectionError("down")
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": DINGZ_HOST}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_duplicate_aborts(hass: HomeAssistant, mock_dingz_client) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DINGZ_ID,
        data={CONF_BASE_URL: BASE_URL},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": DINGZ_HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "device_already_configured"


async def test_zeroconf_discovery(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=ZeroconfServiceInfo(
            ip_address=ip_address(DINGZ_HOST),
            ip_addresses=[ip_address(DINGZ_HOST)],
            hostname="dingz.local.",
            name="dingz._http._tcp.local.",
            port=80,
            properties={"id": DINGZ_ID, "mac": "246f28aabbcc"},
            type="_http._tcp.local.",
        ),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DINGZ_ID


async def test_zeroconf_false_positive(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=ZeroconfServiceInfo(
            ip_address=ip_address(DINGZ_HOST),
            ip_addresses=[ip_address(DINGZ_HOST)],
            hostname="other.local.",
            name="other._http._tcp.local.",
            port=80,
            properties={},
            type="_http._tcp.local.",
        ),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "false_positive"


async def test_id_fallback_to_mac(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    mock_dingz_client.get_system_config = AsyncMock(
        return_value=system_config(id=None, dingz_name="Salon")
    )
    mock_dingz_client.get_info = AsyncMock(return_value={"mac": "246F28AABBCC"})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": DINGZ_HOST}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "246F28AABBCC"
