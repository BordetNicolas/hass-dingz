"""Shared entity mixins for the Dingz integration."""

from __future__ import annotations

import abc
import asyncio
from typing import Any, cast

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import api
from .const import COMMAND_REFRESH_DELAY
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


class DingzOutputEntity(DingzEntity, UserAssignedNameMixin):
    def __init__(self, coordinator: DingzCoordinator, *, index: int) -> None:
        super().__init__(coordinator)
        self._index = index

    @property
    def comp_index(self) -> int:
        return self._index

    @property
    def dingz_dimmer(self) -> api.StateDimmer:
        try:
            return self.coordinator.data["dimmers"][self._index]
        except LookupError:
            return api.StateDimmer()

    @property
    def dingz_output_config(self) -> api.OutputConfig:
        try:
            return self.coordinator.device_config.outputs[self._index]
        except LookupError:
            return api.OutputConfig()

    @property
    def user_given_name(self) -> str | None:
        return self.dingz_output_config.get("name")


class CoordinatedNotificationStateEntity(
    DingzEntity, InternalNotificationMixin, abc.ABC
):
    def __init__(self, runtime: DingzRuntime) -> None:
        InternalNotificationMixin.__init__(self, runtime)
        DingzEntity.__init__(self, runtime.coordinator)

    @callback
    @abc.abstractmethod
    def handle_state_update(self) -> None: ...

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
