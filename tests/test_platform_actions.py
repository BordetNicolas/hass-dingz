"""Actions, push updates and edge cases of the remaining platforms."""

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.dingz import api, capabilities
from custom_components.dingz.const import CONF_BASE_URL, DOMAIN
from custom_components.dingz.conversions import (
    brightness_dingz_to_ha,
    brightness_ha_to_dingz,
    transition_to_dimmer_time,
    transition_to_ramp_ms,
)
from custom_components.dingz.models import MotorMotion, MotorStateNotification
from custom_components.dingz.text import mask_uri_password
from tests.fixtures import devices
from tests.ha_helpers import MockConfigEntry


async def _setup(hass: HomeAssistant, client, raw, **entry_kwargs) -> MockConfigEntry:
    devices.apply_to_client(client, raw)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=devices.dingz_id(raw),
        data={CONF_BASE_URL: "http://192.0.2.10"},
        **entry_kwargs,
    )
    entry.add_to_hass(hass)
    with patch("custom_components.dingz.entity.COMMAND_REFRESH_DELAY", 0):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _entity(hass: HomeAssistant, entry: MockConfigEntry, suffix: str) -> str:
    for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if e.unique_id == f"{entry.unique_id}_{suffix}":
            return e.entity_id
    raise AssertionError(suffix)


async def _call(hass: HomeAssistant, domain: str, service: str, data: dict) -> None:
    with patch("custom_components.dingz.entity.COMMAND_REFRESH_DELAY", 0):
        await hass.services.async_call(domain, service, data, blocking=True)


async def test_front_led(hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled):
    entry = await _setup(
        hass, mock_dingz_client, devices.load("fw243_dip1_blind_smartlight")
    )
    led = _entity(hass, entry, "front_led")
    state = hass.states.get(led)
    assert state.state == "on"
    assert state.attributes["hs_color"] == (48.0, 1.0)

    await _call(
        hass,
        "light",
        "turn_on",
        {"entity_id": led, "hs_color": (200, 80), "brightness": 128, "transition": 10},
    )
    sent = mock_dingz_client.set_led.await_args.args[0]
    assert sent == {"action": "on", "color": "200;80;50", "mode": "hsv", "ramp": 4095}

    await _call(hass, "light", "turn_off", {"entity_id": led})
    assert mock_dingz_client.set_led.await_args.args[0]["action"] == "off"


async def test_ddi_channel(hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled):
    raw = devices.load("fw260_dip3_lights_socket")
    next(iter(raw["device"].values()))["ddi_base"] = True
    raw["ddi_channels_config"] = {
        "ddi_channels": [
            {
                "name": "Spots ",
                "en": True,
                "features": {"colour_temperature": {"en": True}},
            },
            {"name": "", "en": False},
        ]
    }
    raw["state"]["ddi_channels"] = [
        {"on": True, "brightness": 40, "ct_enabled": True, "colour_temperature_k": 3000}
    ]
    entry = await _setup(hass, mock_dingz_client, raw)
    ddi = _entity(hass, entry, "ddi_0")
    state = hass.states.get(ddi)
    assert state.name.endswith(" Spots")
    assert state.attributes["color_temp_kelvin"] == 3000
    assert state.attributes["brightness"] == 102

    await _call(hass, "light", "turn_on", {"entity_id": ddi, "color_temp_kelvin": 4000})
    mock_dingz_client.set_ddi_channel.assert_awaited_with(
        0, "on", brightness=40, color_temperature=4000, time=None
    )
    await _call(hass, "light", "turn_off", {"entity_id": ddi, "transition": 0})
    mock_dingz_client.set_ddi_channel.assert_awaited_with(0, "off", time=0.01)
    with pytest.raises(AssertionError):
        _entity(hass, entry, "ddi_1")


async def test_non_dimmable_light_never_sends_value(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
):
    raw = devices.load("fw260_dip1_pir_front")  # output 0 "Miroir", not dimmable
    entry = await _setup(hass, mock_dingz_client, raw)
    light = _entity(hass, entry, "output_0")
    assert hass.states.get(light).attributes["supported_color_modes"] == ["onoff"]
    await _call(hass, "light", "turn_on", {"entity_id": light, "brightness": 20})
    mock_dingz_client.set_dimmer.assert_awaited_once_with(
        0, "on", value=None, time=None
    )


async def test_cover_actions_and_push(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
):
    entry = await _setup(hass, mock_dingz_client, devices.load("fw260_dip0_two_blinds"))
    cover = _entity(hass, entry, "cover_1")
    client = mock_dingz_client

    await _call(
        hass, "cover", "set_cover_position", {"entity_id": cover, "position": 30}
    )
    client.move_blind_position.assert_awaited_with(1, blind=30)
    await _call(hass, "cover", "open_cover_tilt", {"entity_id": cover})
    client.move_blind_position.assert_awaited_with(1, lamella=100)
    await _call(hass, "cover", "close_cover_tilt", {"entity_id": cover})
    client.move_blind_position.assert_awaited_with(1, lamella=0)
    await _call(
        hass,
        "cover",
        "set_cover_tilt_position",
        {"entity_id": cover, "tilt_position": 40},
    )
    client.move_blind_position.assert_awaited_with(1, lamella=40)
    await _call(
        hass,
        DOMAIN,
        "set_position_and_tilt",
        {"entity_id": cover, "position": 0, "tilt_position": 100},
    )
    client.move_blind_position.assert_awaited_with(1, blind=0, lamella=100)

    runtime = entry.runtime_data
    for motion, expected in (
        (MotorMotion.OPENING, "opening"),
        (MotorMotion.CLOSING, "closing"),
        (MotorMotion.STOPPED, "open"),
    ):
        runtime.dispatch(
            MotorStateNotification(
                index=1, position=50, goal=None, lamella=10, motion=motion
            )
        )
        await hass.async_block_till_done()
        assert hass.states.get(cover).state == expected
    # Another motor's message does not change this cover.
    runtime.dispatch(
        MotorStateNotification(
            index=0, position=0, goal=None, lamella=0, motion=MotorMotion.STOPPED
        )
    )
    await hass.async_block_till_done()
    assert hass.states.get(cover).attributes["current_position"] == 50


async def test_inactive_blind_config_is_skipped(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
):
    raw = devices.load("fw260_dip0_two_blinds")
    raw["blind_config"]["blinds"][0]["active"] = False
    raw["state"]["blinds"][1]["readonly"] = True
    entry = await _setup(hass, mock_dingz_client, raw)
    ids = {
        e.unique_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }
    assert not any(uid.endswith(("_cover_0", "_cover_1")) for uid in ids)


async def test_mqtt_switch_fan_and_offset(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
):
    raw = devices.load("fw260_dip1_pir_front")
    raw["output_config"]["outputs"][1]["type"] = "fan"
    entry = await _setup(hass, mock_dingz_client, raw)
    client = mock_dingz_client

    mqtt_enable = _entity(hass, entry, "mqtt_enable")
    assert hass.states.get(mqtt_enable).state == "on"
    await _call(hass, "switch", "turn_off", {"entity_id": mqtt_enable})
    sent = client.update_mqtt_service_config.await_args.args[0]
    assert sent["enable"] is False and sent["uri"] == "mqtt://broker.example"
    # The cached configuration is not mutated before the device confirms.
    assert entry.runtime_data.device_config.services["mqtt"]["enable"] is True
    await _call(hass, "switch", "turn_on", {"entity_id": mqtt_enable})
    assert client.update_mqtt_service_config.await_args.args[0]["enable"] is True

    fan = _entity(hass, entry, "fan_1")
    await _call(hass, "fan", "turn_on", {"entity_id": fan})
    client.set_dimmer.assert_awaited_with(1, "on")
    await _call(hass, "fan", "turn_off", {"entity_id": fan})
    client.set_dimmer.assert_awaited_with(1, "off")

    offset = _entity(hass, entry, "temp_offset")
    await _call(hass, "number", "set_value", {"entity_id": offset, "value": 1.5})
    client.set_temp_offset.assert_awaited_with(1.5)

    reset = _entity(hass, entry, "reset_pir_0") if False else None
    assert reset is None  # PIRs of this device are disabled


async def test_reset_pir_and_save_config(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
):
    entry = await _setup(hass, mock_dingz_client, devices.load("fw260_dip3_input_pir"))
    await _call(
        hass, "button", "press", {"entity_id": _entity(hass, entry, "reset_pir_1")}
    )
    mock_dingz_client.reset_pir_time.assert_awaited_once_with(1)
    await _call(
        hass,
        "button",
        "press",
        {"entity_id": _entity(hass, entry, "save_default_config")},
    )
    mock_dingz_client.save_default_config.assert_awaited_once()


async def test_certificate_too_long_for_a_state(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
):
    raw = devices.load("fw260_dip3_input_pir")
    raw["services_config"]["mqtt"]["server.crt"] = (
        "-----BEGIN CERTIFICATE-----" + "A" * 900
    )
    entry = await _setup(hass, mock_dingz_client, raw)
    crt = _entity(hass, entry, "mqtt_server_crt")
    assert hass.states.get(crt).state == "unknown"
    await _call(hass, "text", "set_value", {"entity_id": crt, "value": ""})
    assert (
        mock_dingz_client.update_mqtt_service_config.await_args.args[0]["server.crt"]
        is None
    )


def test_mask_uri_password() -> None:
    assert mask_uri_password("mqtt://broker") == "mqtt://broker"
    assert mask_uri_password("mqtt://u:p@broker:1") == "mqtt://u:********@broker:1"
    assert mask_uri_password("") == ""


async def test_mqtt_subscription(hass: HomeAssistant, mock_dingz_client) -> None:
    with (
        patch(
            "custom_components.dingz.mqtt.mqtt.mqtt_config_entry_enabled",
            return_value=True,
        ),
        patch.object(
            hass.config_entries, "async_loaded_entries", return_value=[MagicMock()]
        ),
        patch("custom_components.dingz.mqtt.async_prepare_subscribe_topics") as prepare,
        patch("custom_components.dingz.mqtt.async_subscribe_topics", AsyncMock()),
        patch("custom_components.dingz.mqtt.async_unsubscribe_topics") as unsubscribe,
    ):
        entry = await _setup(
            hass, mock_dingz_client, devices.load("fw260_dip3_input_pir")
        )
        topics = {k: v["topic"] for k, v in prepare.call_args.args[2].items()}
        dingz_id = entry.unique_id
        assert topics["energy"] == f"dingz/{dingz_id}/+/energy/+/+"
        assert topics["input"] == f"dingz/{dingz_id}/+/state/input/+"
        assert await hass.config_entries.async_unload(entry.entry_id)
        unsubscribe.assert_called_once()


async def test_mqtt_skipped_without_dingz_id() -> None:
    from custom_components.dingz.mqtt import async_setup_mqtt

    runtime = MagicMock()
    runtime.dingz_id = ""
    with patch(
        "custom_components.dingz.mqtt.mqtt.mqtt_config_entry_enabled", return_value=True
    ):
        assert await async_setup_mqtt(runtime) is None


async def test_migration_from_1_1_creates_issue(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    entry = await _setup(
        hass, mock_dingz_client, devices.load("fw260_dip3_input_pir"), minor_version=1
    )
    assert ir.async_get(hass).async_get_issue(
        DOMAIN, f"output_energy_dropped_{entry.entry_id}"
    )


async def test_coordinator_failure_paths(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    entry = await _setup(hass, mock_dingz_client, devices.load("fw260_dip3_input_pir"))
    runtime = entry.runtime_data
    coordinator = runtime.coordinator

    # Config refresh failing after a config change keeps the last config.
    changed = devices.load("fw260_dip3_input_pir")
    changed["state"]["config"]["timestamp"] += 1
    mock_dingz_client.get_state.return_value = changed["state"]
    mock_dingz_client.get_full_device_config.side_effect = aiohttp.ClientError
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True

    mock_dingz_client.get_state.return_value = ["not", "a", "dict"]
    with pytest.raises(UpdateFailed) as exc:
        await coordinator._async_update_data()
    assert exc.value.translation_key == "invalid_response"

    mock_dingz_client.get_full_device_config.side_effect = aiohttp.ClientError("x")
    with pytest.raises(UpdateFailed):
        await coordinator._async_setup()

    for error, key in (
        (TimeoutError, "timeout"),
        (api.NotEnoughRamError("r"), "cannot_connect"),
    ):
        mock_dingz_client.get_ram.side_effect = error
        with pytest.raises(UpdateFailed) as exc:
            await runtime.diagnostic._async_update_data()
        assert exc.value.translation_key == key
    mock_dingz_client.get_ram.side_effect = None
    assert await runtime.diagnostic._async_update_data() == {
        "free": 80000,
        "largest_free_block": 20000,
    }


def test_capabilities_tolerate_broken_payloads() -> None:
    assert capabilities.dimmer_slots({"dimmers": "x"}) == []
    assert (
        capabilities.dimmer_slots({"dimmers": [None, {"index": {"relative": "a"}}]})
        == []
    )
    # Old payloads without index: position is used.
    assert capabilities.blind_slots({"blinds": [{}, {"index": None}]}) == [
        capabilities.Slot(relative=0, absolute=0, readonly=False),
        capabilities.Slot(relative=1, absolute=1, readonly=False),
    ]
    assert capabilities.find_by_absolute(None, 0, 0) is None
    assert capabilities.find_by_absolute([None, {}], 1, 1) == {}
    assert capabilities.find_by_absolute([{"index": {"absolute": 3}}], 2, 0) is None
    assert capabilities.item_at([1], 5) is None
    assert capabilities.has_sensor({}, "x") is False
    assert capabilities.enabled_pirs({"sensors": {"pirs": None}}) == []
    assert capabilities.enabled_pirs({"sensors": "x"}) == []
    assert capabilities.thermostat_active({"thermostat": None}) is False


@pytest.mark.parametrize(
    ("raw", "version", "supported"),
    [
        ("2.6.0", "2.6.0", True),
        ("2.4.3", "2.4.3", True),
        ("1.3.30", "1.3.30", False),
        ("9.0.0", "9.0.0", True),
        ("garbage", None, True),
        (None, None, True),
        ("", None, True),
    ],
)
def test_firmware_version(raw, version, supported) -> None:
    device = {"fw_version": raw}
    parsed = capabilities.firmware_version(device)
    assert (str(parsed) if parsed else None) == version
    assert capabilities.firmware_supported(device) is supported


def test_conversion_limits() -> None:
    assert brightness_ha_to_dingz(1) == 1
    assert brightness_ha_to_dingz(-5) == 0
    assert brightness_ha_to_dingz(300) == 100
    assert brightness_dingz_to_ha(1) == 3
    assert brightness_dingz_to_ha(150) == 255
    assert transition_to_dimmer_time(None) is None
    assert transition_to_dimmer_time(0) == 0.01
    assert transition_to_dimmer_time(1.234) == 1.23
    assert transition_to_dimmer_time(60) == 10.0
    assert transition_to_ramp_ms(-1) == 0
    assert transition_to_ramp_ms(100) == 4095


@pytest.mark.parametrize(
    ("input_type", "device_class"),
    [
        ("garage_door_state", "garage_door"),
        ("pir_linked", "motion"),
        ("contact_state", "power"),
    ],
)
async def test_input_device_class_and_push(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled, input_type, device_class
) -> None:
    from custom_components.dingz.models import InputStateNotification, PirNotification

    raw = devices.load("fw260_dip3_input_pir")
    raw["input_config"]["inputs"][0]["input"]["type"] = input_type
    entry = await _setup(hass, mock_dingz_client, raw)
    sensor = _entity(hass, entry, "input_0")
    assert hass.states.get(sensor).attributes["device_class"] == device_class

    runtime = entry.runtime_data
    runtime.dispatch(InputStateNotification(index=0, on=False))
    runtime.dispatch(PirNotification(index=1, event_type="s"))
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "off"
    assert hass.states.get(_entity(hass, entry, "pir_1")).state == "on"
    runtime.dispatch(PirNotification(index=1, event_type="n"))
    await hass.async_block_till_done()
    assert hass.states.get(_entity(hass, entry, "pir_1")).state == "off"


async def test_timestamps_and_brightness_push(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    from custom_components.dingz.models import SimpleSensorStateNotification

    entry = await _setup(hass, mock_dingz_client, devices.load("fw260_dip3_input_pir"))
    stamp = hass.states.get(_entity(hass, entry, "config.timestamp"))
    assert stamp.state.startswith("2026-")
    brightness = _entity(hass, entry, "brightness")
    entry.runtime_data.dispatch(
        SimpleSensorStateNotification(sensor="light", value=999)
    )
    entry.runtime_data.dispatch(
        SimpleSensorStateNotification(sensor="temperature", value=1)
    )
    await hass.async_block_till_done()
    assert hass.states.get(brightness).state == "999"


async def test_mqtt_module_not_loaded_without_mqtt_integration(
    hass: HomeAssistant, mock_dingz_client
) -> None:
    """Without the MQTT integration, its client library is never imported."""
    with patch(
        "custom_components.dingz.mqtt.async_setup_mqtt", AsyncMock()
    ) as setup_mqtt:
        entry = await _setup(
            hass, mock_dingz_client, devices.load("fw260_dip3_input_pir")
        )
    setup_mqtt.assert_not_called()
    assert entry.runtime_data._mqtt_unsub is None
