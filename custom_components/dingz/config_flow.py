"""Config flow for the Dingz integration."""

import json
import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
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
        vol.Required("host"): str,
    }
)

# Distinct from 'already_configured' so MQTT discovery keeps scanning other devices.
_ERROR_DEVICE_ALREADY_CONFIGURED = "device_already_configured"


async def _resolve_dingz_id(client: api.Client, system_config: api.SystemConfig) -> str:
    if dingz_id := system_config.get("id"):
        return dingz_id
    info = await client.get_info()
    if mac := info.get("mac"):
        return str(mac)
    raise CannotConnect


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    base_url = URL(data["host"])
    if not base_url.is_absolute():
        base_url = URL(f"http://{base_url}")

    client = api.Client(async_get_clientsession(hass), base_url)
    try:
        system_config = await client.get_system_config()
        dingz_id = await _resolve_dingz_id(client, system_config)
    except (TimeoutError, aiohttp.ClientError, api.NotEnoughRamError) as err:
        _LOGGER.debug("failed to get system config: %s", err)
        raise CannotConnect from err

    dingz_name = system_config.get("dingz_name")
    room_name = system_config.get("room_name")
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
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                if dingz_id := self._info["dingz_id"]:
                    await self.async_set_unique_id(dingz_id)
                    self._abort_if_unique_id_configured(
                        error=_ERROR_DEVICE_ALREADY_CONFIGURED
                    )
                return await self.async_step_confirm()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
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
        return self.async_show_form(step_id="confirm")

    async def async_step_mqtt(
        self, discovery_info: MqttServiceInfo
    ) -> config_entries.ConfigFlowResult:
        _LOGGER.debug("discovered potential device using mqtt: %s", discovery_info)
        try:
            payload = json.loads(discovery_info.payload)
        except json.JSONDecodeError:
            return self.async_abort(reason="false_positive")
        try:
            ip = str(payload["ip"])
        except KeyError:
            return self.async_abort(reason="false_positive")

        topic_levels = discovery_info.topic.split("/")
        try:
            dingz_id = topic_levels[1]
        except IndexError:
            return self.async_abort(reason="false_positive")

        _LOGGER.debug("mqtt discovery: id=%s, ip=%s", dingz_id, ip)
        await self.async_set_unique_id(dingz_id)
        self._abort_if_unique_id_configured(
            {
                CONF_BASE_URL: f"http://{ip}",
            },
            error=_ERROR_DEVICE_ALREADY_CONFIGURED,
        )

        self._info = await validate_input(self.hass, {"host": ip})
        return await self.async_step_confirm()

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> config_entries.ConfigFlowResult:
        _LOGGER.debug("discovered potential device using zeroconf: %s", discovery_info)
        try:
            dingz_id = str(discovery_info.properties["id"])
        except KeyError:
            return self.async_abort(reason="false_positive")

        _LOGGER.debug("zeroconf discovery: id=%s, ip=%s", dingz_id, discovery_info.host)
        await self.async_set_unique_id(dingz_id)
        self._abort_if_unique_id_configured(
            {
                CONF_BASE_URL: f"http://{discovery_info.host}",
            },
            error=_ERROR_DEVICE_ALREADY_CONFIGURED,
        )

        self._info = await validate_input(self.hass, {"host": discovery_info.host})
        return await self.async_step_confirm()


class CannotConnect(HomeAssistantError): ...
