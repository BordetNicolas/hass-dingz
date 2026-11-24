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


async def test_user_flow_invalid_host(hass: HomeAssistant, mock_dingz_client) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    for bad in ("   ", "ftp://192.168.2.42", "http://"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": bad}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"]["base"] == "invalid_host"
    mock_dingz_client.get_system_config.assert_not_awaited()


async def test_user_flow_strips_path_and_keeps_https(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": " https://dingz.local:8443/api/v1 "}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["data"][CONF_BASE_URL] == "https://dingz.local:8443"


async def test_user_flow_updates_address_of_known_device(
    hass: HomeAssistant, mock_dingz_client
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DINGZ_ID, data={CONF_BASE_URL: "http://192.168.2.1"}
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": DINGZ_HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert entry.data[CONF_BASE_URL] == BASE_URL


async def test_zeroconf_new_ip_updates_existing_entry(
    hass: HomeAssistant, mock_dingz_client
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DINGZ_ID, data={CONF_BASE_URL: "http://192.168.2.1"}
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf(),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "device_already_configured"
    assert entry.data[CONF_BASE_URL] == BASE_URL
    mock_dingz_client.get_system_config.assert_not_awaited()


async def test_zeroconf_unreachable_device_aborts(
    hass: HomeAssistant, mock_dingz_client
) -> None:
    mock_dingz_client.get_system_config = AsyncMock(side_effect=TimeoutError)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=_zeroconf()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


def _mqtt(topic: str, payload: str):
    from homeassistant.helpers.service_info.mqtt import MqttServiceInfo

    return MqttServiceInfo(
        topic=topic,
        payload=payload,
        qos=0,
        retain=True,
        subscribed_topic="dingz/+/announce",
        timestamp=0,
    )


def _zeroconf() -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ip_address(DINGZ_HOST),
        ip_addresses=[ip_address(DINGZ_HOST)],
        hostname="dingz.local.",
        name="dingz._http._tcp.local.",
        port=80,
        properties={"id": DINGZ_ID},
        type="_http._tcp.local.",
    )


async def test_mqtt_discovery(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    payload = '{"model":"dz1f-4b","ip":"192.168.2.42","fw_version":"2.6.0"}'
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_MQTT},
        data=_mqtt(f"dingz/{DINGZ_ID}/announce", payload),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"]["url"] == BASE_URL


@pytest.mark.parametrize(
    ("topic", "payload"),
    [
        ("dingz/x/announce", "not json"),
        ("dingz/x/announce", "[1, 2]"),
        ("dingz/x/announce", '{"model": "dz1f-4b"}'),
        ("dingz", '{"ip": "192.168.2.42"}'),
    ],
)
async def test_mqtt_discovery_false_positive(
    hass: HomeAssistant, topic: str, payload: str
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_MQTT},
        data=_mqtt(topic, payload),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "false_positive"


async def test_mqtt_discovery_unreachable(
    hass: HomeAssistant, mock_dingz_client
) -> None:
    mock_dingz_client.get_system_config = AsyncMock(
        side_effect=aiohttp.ClientConnectionError("down")
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_MQTT},
        data=_mqtt(f"dingz/{DINGZ_ID}/announce", '{"ip": "192.168.2.42"}'),
    )
    assert result["reason"] == "cannot_connect"


async def _start_reconfigure(hass: HomeAssistant, entry: MockConfigEntry):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )


async def test_reconfigure_changes_address(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DINGZ_ID, data={CONF_BASE_URL: "http://192.168.2.1"}
    )
    entry.add_to_hass(hass)
    result = await _start_reconfigure(hass, entry)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "nope://"}
    )
    assert result["errors"]["base"] == "invalid_host"

    mock_dingz_client.get_system_config.side_effect = TimeoutError
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": DINGZ_HOST}
    )
    assert result["errors"]["base"] == "cannot_connect"

    mock_dingz_client.get_system_config.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": DINGZ_HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_BASE_URL] == BASE_URL
    await hass.async_block_till_done()


async def test_reconfigure_rejects_other_device(
    hass: HomeAssistant, mock_dingz_client
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="another", data={CONF_BASE_URL: "http://192.168.2.1"}
    )
    entry.add_to_hass(hass)
    result = await _start_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": DINGZ_HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert entry.data[CONF_BASE_URL] == "http://192.168.2.1"


async def test_no_id_and_no_mac_cannot_connect(
    hass: HomeAssistant, mock_dingz_client
) -> None:
    mock_dingz_client.get_system_config = AsyncMock(return_value=system_config(id=None))
    mock_dingz_client.get_info = AsyncMock(return_value={})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": DINGZ_HOST}
    )
    assert result["errors"]["base"] == "cannot_connect"
