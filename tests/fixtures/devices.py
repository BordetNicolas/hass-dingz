"""Anonymized REST payloads captured from real dingz devices.

Each JSON file holds the GET responses of one device (``device``, ``state``,
``*_config``). MAC, IP, SSID, serial numbers, MQTT URI and coordinates are
replaced. Captured on 2026-11-24:

- ``fw243_dip1_blind_smartlight``: firmware 2.4.3, DIP 1 (2 dimmers + 1 motor
  on absolute motor 1), outputs 0-1 ``smart_light``, no PIR front.
- ``fw260_dip0_two_blinds``: firmware 2.6.0, DIP 0 (2 motors, no dimmer).
- ``fw260_dip1_pir_front``: firmware 2.6.0, DIP 1, PIR front, output 0
  ``light``, output 1 ``smart_light``.
- ``fw260_dip3_lights_socket``: firmware 2.6.0, DIP 3 (4 dimmers), three
  ``smart_light`` and one ``power_socket``.
- ``fw260_dip3_input_pir``: firmware 2.6.0, DIP 3, input active (output 0
  read-only), outputs 2-3 inactive, PIR front.
"""

from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

from custom_components.dingz import api

DEVICES_DIR = Path(__file__).parent / "devices"

ALL_DEVICES = (
    "fw243_dip1_blind_smartlight",
    "fw260_dip0_two_blinds",
    "fw260_dip1_pir_front",
    "fw260_dip3_lights_socket",
    "fw260_dip3_input_pir",
)


@cache
def _raw(name: str) -> dict[str, Any]:
    return json.loads((DEVICES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def load(name: str) -> dict[str, Any]:
    """A fresh deep copy, safe to mutate in a test."""
    return copy.deepcopy(_raw(name))


def dingz_id(raw: dict[str, Any]) -> str:
    return raw["system_config"]["id"]


def full_config(raw: dict[str, Any]) -> api.FullDeviceConfig:
    """Same assembly as ``api.Client.get_full_device_config``."""
    return api.FullDeviceConfig(
        device=next(iter(raw["device"].values())),
        system=raw["system_config"],
        services=raw["services_config"],
        inputs=raw["input_config"].get("inputs", []),
        outputs=raw["output_config"].get("outputs", []),
        blinds=raw["blind_config"].get("blinds", []),
        buttons=raw["button_config"],
        ddi_channels=raw["ddi_channels_config"].get("ddi_channels", []),
    )


def apply_to_client(client: Any, raw: dict[str, Any]) -> None:
    """Point a mocked ``api.Client`` at a captured device."""
    client.get_system_config.return_value = raw["system_config"]
    client.get_state.return_value = raw["state"]
    client.get_full_device_config.return_value = full_config(raw)
