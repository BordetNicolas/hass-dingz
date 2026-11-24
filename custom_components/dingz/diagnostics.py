"""Diagnostics support for Dingz."""

from __future__ import annotations

import dataclasses
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import capabilities
from .const import CONF_BASE_URL
from .coordinator import DingzConfigEntry

TO_REDACT = {
    CONF_BASE_URL,
    # The dingz id is its MAC address.
    "id",
    "uri",
    "server.crt",
    "aws_default_cert",
    "ssid",
    "mac",
    "ip",
    "mask",
    "gateway",
    "gw",
    "dns",
    "lat",
    "long",
    "puck_sn",
    "front_sn",
    "hash",
    "targets",
    "st_dingz_id",
    "rest_password",
    "home_name",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DingzConfigEntry
) -> dict[str, Any]:
    runtime = entry.runtime_data
    config = runtime.device_config
    state = runtime.coordinator.data or {}
    device = dict(config.device)
    version = capabilities.firmware_version(device)
    return {
        "entry": async_redact_data(
            {"data": dict(entry.data), "version": entry.version}, TO_REDACT
        ),
        "firmware": {
            "version": str(version) if version else None,
            "supported": capabilities.firmware_supported(device),
        },
        "capabilities": {
            "dimmers": [
                dataclasses.asdict(s) for s in capabilities.dimmer_slots(state)
            ],
            "blinds": [dataclasses.asdict(s) for s in capabilities.blind_slots(state)],
            "enabled_pirs": capabilities.enabled_pirs(state),
            "mqtt_enabled": capabilities.mqtt_enabled(config),
            "thermostat_active": capabilities.thermostat_active(state),
        },
        "last_update_success": runtime.coordinator.last_update_success,
        "device_config": async_redact_data(dataclasses.asdict(config), TO_REDACT),
        "state": async_redact_data(dict(state), TO_REDACT),
    }
