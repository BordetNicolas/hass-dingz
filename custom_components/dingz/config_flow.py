"""Config flow for the Dingz integration."""

import json
import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.mqtt import MqttServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from yarl import URL

from . import api
from .const import CONF_BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
    }
)

# Distinct from 'already_configured' so MQTT discovery keeps scanning other devices.
_ERROR_DEVICE_ALREADY_CONFIGURED = "device_already_configured"


def normalize_base_url(raw: str) -> URL:
    """Turn a host, IP or URL into the device base URL (HTTP by default)."""
    raw = raw.strip()
    if not raw:
        raise InvalidHost
    try:
        url = URL(raw) if "://" in raw else URL(f"http://{raw}")
    except ValueError as err:
        raise InvalidHost from err
    if url.scheme not in ("http", "https") or not url.host:
        raise InvalidHost
    # Only scheme, host and port are meaningful: the client appends /api/v1.
    return url.origin()


async def _resolve_dingz_id(client: api.Client, system_config: api.SystemConfig) -> str:
    if dingz_id := system_config.get("id"):
        return dingz_id
    info = await client.get_info()
    if isinstance(info, dict) and (mac := info.get("mac")):
        return str(mac)
    raise CannotConnect


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    base_url = normalize_base_url(data[CONF_HOST])

    client = api.Client(async_get_clientsession(hass), base_url)
    try:
        system_config = await client.get_system_config()
        if not isinstance(system_config, dict):
            raise CannotConnect
        dingz_id = await _resolve_dingz_id(client, system_config)
    except (TimeoutError, aiohttp.ClientError, api.NotEnoughRamError) as err:
        _LOGGER.debug("failed to get system config: %s", err)
        raise CannotConnect from err

    dingz_name = (system_config.get("dingz_name") or "").strip()
    room_name = (system_config.get("room_name") or "").strip()
    if dingz_name and room_name:
        title = f"{room_name} - {dingz_name}"
    elif dingz_name:
        title = dingz_name
    else:
        title = dingz_id

    return {
        "title": title,
        "dingz_id": dingz_id,
        "data": {CONF_BASE_URL: str(base_url)},
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        super().__init__()
        self._info: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._info = await validate_input(self.hass, user_input)
            except InvalidHost:
                errors["base"] = "invalid_host"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(self._info["dingz_id"])
                self._abort_if_unique_id_configured(
                    updates=self._info["data"],
                    error=_ERROR_DEVICE_ALREADY_CONFIGURED,
                )
                return await self.async_step_confirm()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        assert self._info
        if user_input is not None:
            return self.async_create_entry(
                title=self._info["title"], data=self._info["data"]
            )

        self.context["title_placeholders"] = {
            "name": self._info["title"],
        }
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._info["title"],
                "url": self._info["data"][CONF_BASE_URL],
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Change the address of an existing Dingz."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except InvalidHost:
                errors["base"] = "invalid_host"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info["dingz_id"])
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates=info["data"]
                )

        suggested = user_input or {CONF_HOST: URL(entry.data[CONF_BASE_URL]).host}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, suggested
            ),
            errors=errors,
        )

    async def _async_discovered(
        self, dingz_id: str, host: str
    ) -> config_entries.ConfigFlowResult:
        await self.async_set_unique_id(dingz_id)
        self._abort_if_unique_id_configured(
            {CONF_BASE_URL: f"http://{host}"},
            error=_ERROR_DEVICE_ALREADY_CONFIGURED,
        )
        try:
            self._info = await validate_input(self.hass, {CONF_HOST: host})
        except (CannotConnect, InvalidHost):
            return self.async_abort(reason="cannot_connect")
        return await self.async_step_confirm()

    async def async_step_mqtt(
        self, discovery_info: MqttServiceInfo
    ) -> config_entries.ConfigFlowResult:
        _LOGGER.debug("discovered potential device using mqtt: %s", discovery_info)
        try:
            payload = json.loads(discovery_info.payload)
        except (json.JSONDecodeError, TypeError):
            return self.async_abort(reason="false_positive")
        if not isinstance(payload, dict) or not payload.get("ip"):
            return self.async_abort(reason="false_positive")

        topic_levels = discovery_info.topic.split("/")
        if len(topic_levels) < 3 or not topic_levels[1]:
            return self.async_abort(reason="false_positive")
        dingz_id = topic_levels[1]

        _LOGGER.debug("mqtt discovery: id=%s, ip=%s", dingz_id, payload["ip"])
        return await self._async_discovered(dingz_id, str(payload["ip"]))

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> config_entries.ConfigFlowResult:
        _LOGGER.debug("discovered potential device using zeroconf: %s", discovery_info)
        dingz_id = discovery_info.properties.get("id")
        if not dingz_id:
            return self.async_abort(reason="false_positive")

        _LOGGER.debug("zeroconf discovery: id=%s, ip=%s", dingz_id, discovery_info.host)
        return await self._async_discovered(str(dingz_id), discovery_info.host)


class CannotConnect(HomeAssistantError): ...


class InvalidHost(HomeAssistantError): ...
