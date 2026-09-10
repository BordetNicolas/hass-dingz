"""JSON payloads matching the Dingz REST API (firmware 2.x / hass-dingz types)."""

from typing import Any

from custom_components.dingz import api

DINGZ_ID = "abcd1234ef"
DINGZ_MAC = "24:6f:28:aa:bb:cc"
DINGZ_HOST = "192.168.2.42"
BASE_URL = f"http://{DINGZ_HOST}"


def system_config(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "dingz_name": "Salon",
        "room_name": "Living",
        "id": DINGZ_ID,
        "temp_offset": 0.0,
        "dyn_light": {"enable": False},
    }
    data.update(overrides)
    return data


def device_response(**overrides: Any) -> dict[str, Any]:
    device: dict[str, Any] = {
        "fw_version": "2.3.0",
        "hw_version": "2",
        "puck_hw_model": "dz1p-4d",
        "front_hw_model": "dz1f-pir",
        "puck_sn": "PSN1",
        "front_sn": "FSN1",
        "has_pir": True,
        "ddi_base": False,
    }
    device.update(overrides)
    return {DINGZ_MAC.replace(":", ""): device}


def output_config(
    *outputs: dict[str, Any],
) -> dict[str, Any]:
    if not outputs:
        outputs = (
            {
                "active": True,
                "name": "Plafond",
                "type": "light",
                "light": {"dimmable": True},
            },
            {
                "active": True,
                "name": "Applique",
                "type": "light",
                "light": {"dimmable": False},
            },
            {
                "active": True,
                "name": "Prise",
                "type": "power_socket",
            },
            {"active": False, "name": "Unused", "type": "light"},
        )
    return {"outputs": list(outputs)}


def input_config(*inputs: dict[str, Any]) -> dict[str, Any]:
    if not inputs:
        inputs = (
            {
                "active": True,
                "name": "Contact",
                "input": {"type": "contact_state"},
            },
            {"active": False, "name": "Off"},
        )
    return {"inputs": list(inputs)}


def button_config(*buttons: dict[str, Any]) -> dict[str, Any]:
    if not buttons:
        buttons = (
            {"active": True, "name": "Btn1"},
            {"active": True, "name": "Btn2"},
            {"active": False, "name": "Btn3"},
            {"active": True, "name": "Btn4"},
        )
    return {"dingz_orientation": "standard", "buttons": list(buttons)}


def blind_config(*blinds: dict[str, Any]) -> dict[str, Any]:
    if not blinds:
        blinds = ({"active": True, "name": "Store"},)
    return {"blinds": list(blinds)}


def services_config(*, mqtt_enable: bool = False) -> dict[str, Any]:
    return {
        "mqtt": {
            "uri": "",
            "enable": mqtt_enable,
            "server.crt": None,
        }
    }


def state_payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "dimmers": [
            {"on": True, "output": 80, "ramp": 0, "readonly": False},
            {"on": False, "output": 0, "ramp": 0, "readonly": False},
            {"on": False, "output": 0, "ramp": 0, "readonly": False},
            {"on": False, "output": 0, "ramp": 0, "readonly": True},
        ],
        "blinds": [
            {"moving": "stop", "position": 40, "lamella": 20, "readonly": False},
        ],
        "led": {
            "on": True,
            "hsv": "120;50;80",
            "rgb": "40bf40",
            "mode": "hsv",
            "ramp": 0,
        },
        "sensors": {
            "brightness": 123,
            "light_state": "day",
            "room_temperature": 21.5,
            "uncompensated_temperature": 22.0,
            "cpu_temperature": 40.0,
            "puck_temperature": 35.0,
            "fet_temperature": 36.0,
            "input_state": True,
            "pirs": [
                {"enabled": True, "motion": False},
                None,
            ],
            "power_outputs": [
                {"value": 12},
                {"value": 0},
                {"value": 5},
                {"value": 0},
            ],
        },
        "thermostat": {
            "active": True,
            "state": "off",
            "mode": "heating",
            "enabled": True,
            "target_temp": 21,
            "min_target_temp": 5,
            "max_target_temp": 35,
            "temp": 21.5,
        },
        "wifi": {
            "mac": DINGZ_MAC.replace(":", ""),
            "ip": DINGZ_HOST,
            "connected": True,
        },
        "config": {"timestamp": 1700000000},
        "ddi_channels": [],
        "time": "2024-01-01T12:00:00",
    }
    data.update(overrides)
    return data


def ram_payload() -> dict[str, int]:
    return {"free": 80000, "largest_free_block": 20000}


def full_device_config(
    *,
    mqtt_enable: bool = False,
    fan: bool = False,
    ddi: bool = False,
) -> api.FullDeviceConfig:
    outputs = output_config()["outputs"]
    if fan:
        outputs = [
            *outputs[:2],
            {"active": True, "name": "VMC", "type": "fan"},
            outputs[3],
        ]
    return api.FullDeviceConfig(
        device=next(iter(device_response(ddi_base=ddi).values())),
        system=system_config(),
        services=services_config(mqtt_enable=mqtt_enable),
        inputs=input_config()["inputs"],
        outputs=outputs,
        blinds=blind_config()["blinds"],
        buttons=button_config(),
        ddi_channels=[],
    )
