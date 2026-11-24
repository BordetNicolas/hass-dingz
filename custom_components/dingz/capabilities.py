"""Capability detection for a single Dingz.

Firmware and DIP-switch configuration differ between devices, so every
platform derives what exists from the payloads returned by the device rather
than from a global firmware version.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any

from awesomeversion import AwesomeVersion, AwesomeVersionException

from . import api

# The REST API documented by iolo (playground v2) requires firmware 2.x.
MIN_SUPPORTED_FIRMWARE = AwesomeVersion("2.0.0")


@dataclasses.dataclass(frozen=True, slots=True)
class Slot:
    """A dimmer or motor exposed by GET /state.

    ``relative`` is the index used by the REST commands and MQTT topics,
    ``absolute`` the physical output (or motor) number used by the
    configuration endpoints.
    """

    relative: int
    absolute: int
    readonly: bool


def _slots(items: Any) -> list[Slot]:
    if not isinstance(items, Sequence):
        return []
    slots: list[Slot] = []
    for position, item in enumerate(items):
        if not isinstance(item, Mapping):
            continue
        index = item.get("index")
        if not isinstance(index, Mapping):
            index = {}
        relative = index.get("relative", position)
        absolute = index.get("absolute", relative)
        if not isinstance(relative, int) or not isinstance(absolute, int):
            continue
        slots.append(
            Slot(
                relative=relative,
                absolute=absolute,
                readonly=bool(item.get("readonly", False)),
            )
        )
    return slots


def dimmer_slots(state: Mapping[str, Any]) -> list[Slot]:
    """Dimmers present with the current DIP configuration."""
    return _slots(state.get("dimmers"))


def blind_slots(state: Mapping[str, Any]) -> list[Slot]:
    """Motors present with the current DIP configuration."""
    return _slots(state.get("blinds"))


def find_by_absolute(items: Any, absolute: int, fallback: int) -> Any | None:
    """Return the state item for a physical index, tolerating missing indexes."""
    if not isinstance(items, Sequence):
        return None
    for position, item in enumerate(items):
        if not isinstance(item, Mapping):
            continue
        index = item.get("index")
        if isinstance(index, Mapping):
            if index.get("absolute") == absolute:
                return item
        elif position == fallback:
            return item
    return None


def item_at(items: Any, index: int) -> Any | None:
    """Safe list access for configuration arrays of variable length."""
    if isinstance(items, Sequence) and 0 <= index < len(items):
        return items[index]
    return None


def has_sensor(state: Mapping[str, Any], key: str) -> bool:
    """Whether GET /state reports a sensor (firmware 2.6.0 dropped some)."""
    sensors = state.get("sensors")
    return isinstance(sensors, Mapping) and sensors.get(key) is not None


def enabled_pirs(state: Mapping[str, Any]) -> list[int]:
    """Indexes of PIR slots reported as enabled."""
    sensors = state.get("sensors")
    if not isinstance(sensors, Mapping):
        return []
    pirs = sensors.get("pirs")
    if not isinstance(pirs, Sequence):
        return []
    return [
        index
        for index, pir in enumerate(pirs)
        if isinstance(pir, Mapping) and pir.get("enabled", False)
    ]


def mqtt_enabled(config: api.FullDeviceConfig) -> bool:
    mqtt = config.services.get("mqtt")
    return isinstance(mqtt, Mapping) and bool(mqtt.get("enable", False))


def thermostat_active(state: Mapping[str, Any]) -> bool:
    thermostat = state.get("thermostat")
    return isinstance(thermostat, Mapping) and bool(thermostat.get("active", False))


def firmware_version(device: Mapping[str, Any]) -> AwesomeVersion | None:
    """Semantic firmware version, or None when missing or unparsable."""
    raw = device.get("fw_version")
    if not isinstance(raw, str) or not raw:
        return None
    version = AwesomeVersion(raw)
    try:
        # Accessing ``major`` validates that the version is usable.
        if version.major is None:
            return None
    except AwesomeVersionException:
        return None
    return version


def firmware_supported(device: Mapping[str, Any]) -> bool:
    """Unknown or future versions are accepted; only known-old ones are not."""
    version = firmware_version(device)
    if version is None:
        return True
    try:
        return version >= MIN_SUPPORTED_FIRMWARE
    except AwesomeVersionException:
        return True


def structure_signature(
    config: api.FullDeviceConfig, state: Mapping[str, Any]
) -> tuple[Any, ...]:
    """Everything that decides which entities are created.

    When it changes after a configuration change on the device, the config
    entry is reloaded so entities follow the new configuration.
    """
    return (
        tuple(
            (o.get("active"), o.get("type"), (o.get("light") or {}).get("dimmable"))
            for o in config.outputs
        ),
        tuple((b.get("active"), b.get("type")) for b in config.blinds),
        tuple(i.get("active") for i in config.inputs),
        tuple(b.get("active") for b in config.buttons.get("buttons", [])),
        tuple(ch.get("en") for ch in config.ddi_channels),
        bool(config.device.get("ddi_base", False)),
        bool((config.system.get("dyn_light") or {}).get("enable", False)),
        mqtt_enabled(config),
        tuple(dimmer_slots(state)),
        tuple(blind_slots(state)),
        tuple(enabled_pirs(state)),
        thermostat_active(state),
    )
