"""Data update coordinators and runtime objects for Dingz."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from yarl import URL

from . import api
from .const import (
    CONF_BASE_URL,
    DIAGNOSTIC_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    REQUEST_TIMEOUT,
    SCAN_INTERVAL,
)
from .models import InternalNotification

_LOGGER = logging.getLogger(__name__)

type DingzConfigEntry = ConfigEntry[DingzRuntime]


class DingzCoordinator(DataUpdateCoordinator[api.State]):
    """Poll GET /api/v1/state and hold relatively static device configuration."""

    def __init__(self, runtime: DingzRuntime) -> None:
        super().__init__(
            runtime.hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=runtime.entry,
            update_interval=SCAN_INTERVAL,
        )
        self.runtime = runtime
        self.device_config = api.FullDeviceConfig(
            device=api.Device(),
            system=api.SystemConfig(),
            services=api.ServicesConfig(),
            inputs=[],
            outputs=[],
            blinds=[],
            buttons=api.ButtonsConfig(),
            ddi_channels=[],
        )
        self._config_timestamp: int | None = None

    async def _async_setup(self) -> None:
        await self.async_refresh_config()

    async def async_refresh_config(self) -> None:
        """Reload the relatively static Dingz configuration."""
        async with asyncio.timeout(REQUEST_TIMEOUT * 6):
            self.device_config = await self.runtime.client.get_full_device_config()
        _LOGGER.debug(
            "loaded device config for %s (outputs=%s blinds=%s)",
            self.runtime.dingz_id or self.device_config.system.get("id"),
            len(self.device_config.outputs),
            len(self.device_config.blinds),
        )

    async def _async_update_data(self) -> api.State:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                state = await self.runtime.client.get_state()
        except TimeoutError as err:
            raise UpdateFailed("Timeout while fetching Dingz state") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with Dingz: {err}") from err
        except api.NotEnoughRamError as err:
            raise UpdateFailed(str(err)) from err

        timestamp = _config_timestamp(state)
        if timestamp is not None and timestamp != self._config_timestamp:
            if self._config_timestamp is not None:
                _LOGGER.debug("config timestamp changed, reloading device config")
                try:
                    await self.async_refresh_config()
                except (
                    TimeoutError,
                    aiohttp.ClientError,
                    api.NotEnoughRamError,
                ) as err:
                    _LOGGER.warning("failed to refresh Dingz config: %s", err)
            self._config_timestamp = timestamp

        return state


class DiagnosticCoordinator(DataUpdateCoordinator[api.Ram]):
    """Optional RAM diagnostics; only polls when entities are enabled."""

    def __init__(self, runtime: DingzRuntime) -> None:
        super().__init__(
            runtime.hass,
            _LOGGER,
            name=f"{DOMAIN}_diag",
            config_entry=runtime.entry,
            update_interval=DIAGNOSTIC_SCAN_INTERVAL,
        )
        self.runtime = runtime

    async def _async_update_data(self) -> api.Ram:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                return await self.runtime.client.get_ram()
        except TimeoutError as err:
            raise UpdateFailed("Timeout while fetching Dingz RAM") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with Dingz: {err}") from err
        except api.NotEnoughRamError as err:
            raise UpdateFailed(str(err)) from err


class DingzRuntime:
    """Objects that live for the lifetime of a config entry."""

    def __init__(self, hass: HomeAssistant, entry: DingzConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.client = api.Client(
            async_get_clientsession(hass), URL(entry.data[CONF_BASE_URL])
        )
        self.coordinator = DingzCoordinator(self)
        self.diagnostic = DiagnosticCoordinator(self)
        self.device_info = DeviceInfo()
        self.dingz_id = entry.unique_id or ""
        self.mac_addr = ""
        self._notifier = _Notifier()
        self._mqtt_unsub: Callable[[], None] | None = None

    @property
    def device_config(self) -> api.FullDeviceConfig:
        return self.coordinator.device_config

    def add_listener(
        self, callback: Callable[[InternalNotification], None]
    ) -> Callable[[], None]:
        return self._notifier.add_listener(callback)

    def dispatch(self, notification: InternalNotification) -> None:
        self._notifier.dispatch(notification)

    async def async_setup(self) -> None:
        """Load config + first state, then fill DeviceInfo and optional MQTT."""
        await self.coordinator.async_config_entry_first_refresh()

        system = self.device_config.system
        if dingz_id := system.get("id"):
            self.dingz_id = dingz_id

        try:
            self.mac_addr = dr.format_mac(self.coordinator.data["wifi"]["mac"])
        except LookupError:
            self.mac_addr = ""

        connections: set[tuple[str, str]] = set()
        if self.mac_addr:
            connections.add((dr.CONNECTION_NETWORK_MAC, self.mac_addr))

        identifiers: set[tuple[str, str]] = set()
        if self.dingz_id:
            identifiers.add((DOMAIN, self.dingz_id))
        elif self.mac_addr:
            identifiers.add((DOMAIN, self.mac_addr))

        self.device_info.update(
            DeviceInfo(
                configuration_url=str(self.client.base_url),
                connections=connections,
                identifiers=identifiers,
                manufacturer=MANUFACTURER,
                model=self.device_config.device.get("puck_hw_model"),
                name=system.get("dingz_name"),
                suggested_area=system.get("room_name"),
                sw_version=self.device_config.device.get("fw_version"),
                hw_version=self.device_config.device.get("hw_version"),
                serial_number=self.dingz_id or None,
            )
        )

        from .mqtt import async_setup_mqtt

        self._mqtt_unsub = await async_setup_mqtt(self)

    async def async_unload(self) -> None:
        if self._mqtt_unsub:
            self._mqtt_unsub()
            self._mqtt_unsub = None


def _config_timestamp(state: api.State) -> int | None:
    config = state.get("config")
    if not isinstance(config, dict):
        return None
    timestamp = config.get("timestamp")
    return timestamp if isinstance(timestamp, int) else None


class _Notifier:
    def __init__(self) -> None:
        self._listeners: dict[
            Callable[[], None], Callable[[InternalNotification], None]
        ] = {}

    def add_listener(
        self, callback: Callable[[InternalNotification], None]
    ) -> Callable[[], None]:
        def remove_listener() -> None:
            self._listeners.pop(remove_listener, None)

        self._listeners[remove_listener] = callback
        return remove_listener

    def dispatch(self, notification: InternalNotification) -> None:
        _LOGGER.debug("dispatching %s", notification)
        for update_callback in list(self._listeners.values()):
            update_callback(notification)
