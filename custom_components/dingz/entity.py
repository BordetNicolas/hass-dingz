"""Shared entity mixins for the Dingz integration."""

from __future__ import annotations

import abc
import asyncio
from collections.abc import Awaitable
from typing import Any, cast

import aiohttp
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import api, capabilities
from .const import COMMAND_REFRESH_DELAY, DOMAIN
from .coordinator import DiagnosticCoordinator, DingzCoordinator, DingzRuntime
from .models import InternalNotification


def compile_json_path(raw: str) -> list[str | int]:
    path = cast(list[str | int], raw.split("."))
    for i, seg in enumerate(path):
        if isinstance(seg, str) and seg.isdigit():
            path[i] = int(seg)
    return path


def json_path_lookup(value: Any, path: list[str | int]) -> Any | None:
    if value is None:
        return None
    try:
        for key in path:
            value = value[key]
    except LookupError:
        return None
    return value


async def async_command[T](awaitable: Awaitable[T]) -> T:
    """Run a REST command and surface failures as a translated HA error."""
    try:
        return await awaitable
    except TimeoutError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="command_timeout"
        ) from err
    except (aiohttp.ClientError, api.NotEnoughRamError) as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="command_failed",
            translation_placeholders={"error": str(err)},
        ) from err


def clean_name(raw: Any) -> str | None:
    """User-given Dingz names often carry trailing spaces."""
    if not isinstance(raw, str):
        return None
    return raw.strip() or None


def entity_unique_id(runtime: DingzRuntime, suffix: str) -> str:
    """Stable unique_id based on the Dingz hardware id, never the IP address."""
    return f"{runtime.dingz_id}_{suffix}"


class DingzEntity(CoordinatorEntity[DingzCoordinator]):
    """Base entity attached to a single Dingz device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DingzCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.runtime.device_info

    @property
    def runtime(self) -> DingzRuntime:
        return self.coordinator.runtime


class UserAssignedNameMixin(Entity, abc.ABC):
    _attr_has_entity_name = True

    @property
    @abc.abstractmethod
    def comp_index(self) -> int: ...

    @property
    @abc.abstractmethod
    def user_given_name(self) -> str | None: ...

    @property
    def name(self) -> str | None:
        name = self.user_given_name or ""

        if name:
            tr_key = (
                f"component.{self.platform.platform_name}.entity."
                f"{self.platform.domain}.{self.translation_key}_named.name"
            )
        else:
            tr_key = (
                f"component.{self.platform.platform_name}.entity."
                f"{self.platform.domain}.{self.translation_key}.name"
            )

        tr_fmt: str | None = self.platform_data.platform_translations.get(tr_key)
        if name and not tr_fmt:
            tr_fmt = "{name}"

        if tr_fmt is None:
            return None
        return tr_fmt.format(name=name, position=self.comp_index + 1)


class InternalNotificationMixin(Entity, abc.ABC):
    _attr_should_poll = False

    def __init__(self, runtime: DingzRuntime) -> None:
        super().__init__()
        self._dingz_runtime = runtime

    @property
    def runtime(self) -> DingzRuntime:
        return self._dingz_runtime

    @callback
    @abc.abstractmethod
    def handle_notification(self, notification: InternalNotification) -> None: ...

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.runtime.add_listener(self.handle_notification))


class DelayedCoordinatorRefreshMixin:
    async def delayed_request_refresh(self) -> None:
        # The dingz updates its internal state a short moment after a command.
        await asyncio.sleep(COMMAND_REFRESH_DELAY)
        coordinator = cast(DingzCoordinator, self.coordinator)  # type: ignore[attr-defined]
        await coordinator.async_request_refresh()


def output_slots(runtime: DingzRuntime, output_type: str) -> list[capabilities.Slot]:
    """Controllable dimmers whose physical output has the given type.

    ``output_config`` always lists the four physical outputs, including those
    driving motors or used as an input; only the dimmers reported by
    GET /state (and not read-only) can be commanded.
    """
    slots = []
    for slot in capabilities.dimmer_slots(runtime.coordinator.data or {}):
        if slot.readonly:
            continue
        config = capabilities.item_at(runtime.device_config.outputs, slot.absolute)
        if (
            isinstance(config, dict)
            and config.get("active", False)
            and config.get("type") == output_type
        ):
            slots.append(slot)
    return slots


class OutputMixin(UserAssignedNameMixin):
    """Access to a physical output and its dimmer state.

    ``_slot.relative`` addresses REST commands; ``_slot.absolute`` addresses
    ``output_config`` and ``power_outputs`` and keeps unique ids stable.
    """

    _slot: capabilities.Slot
    coordinator: DingzCoordinator

    @property
    def comp_index(self) -> int:
        return self._slot.absolute

    @property
    def dingz_dimmer(self) -> api.StateDimmer:
        data = self.coordinator.data or {}
        item = capabilities.find_by_absolute(
            data.get("dimmers"), self._slot.absolute, self._slot.relative
        )
        return item if item is not None else api.StateDimmer()

    @property
    def dingz_output_config(self) -> api.OutputConfig:
        item = capabilities.item_at(
            self.coordinator.device_config.outputs, self._slot.absolute
        )
        return item if item is not None else api.OutputConfig()

    @property
    def user_given_name(self) -> str | None:
        return clean_name(self.dingz_output_config.get("name"))


class DingzOutputEntity(DingzEntity, OutputMixin):
    def __init__(
        self, coordinator: DingzCoordinator, *, slot: capabilities.Slot
    ) -> None:
        super().__init__(coordinator)
        self._slot = slot


class CoordinatedNotificationStateEntity(
    DingzEntity, InternalNotificationMixin, abc.ABC
):
    def __init__(self, runtime: DingzRuntime) -> None:
        InternalNotificationMixin.__init__(self, runtime)
        DingzEntity.__init__(self, runtime.coordinator)

    @callback
    @abc.abstractmethod
    def handle_state_update(self) -> None: ...

    async def async_added_to_hass(self) -> None:
        # Show the state fetched during setup instead of waiting for the
        # next poll.
        if self.coordinator.data is not None:
            self.handle_state_update()
        await super().async_added_to_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.handle_state_update()
        super()._handle_coordinator_update()


class DiagnosticEntity(CoordinatorEntity[DiagnosticCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DiagnosticCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.runtime.device_info

    @property
    def runtime(self) -> DingzRuntime:
        return self.coordinator.runtime
