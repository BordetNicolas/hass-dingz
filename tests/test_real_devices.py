"""End-to-end setup against payloads captured from real dingz (2.4.3 / 2.6.0)."""

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.dingz.const import CONF_BASE_URL, DOMAIN
from tests.fixtures import devices
from tests.ha_helpers import MockConfigEntry


async def _setup(hass: HomeAssistant, client, raw) -> MockConfigEntry:
    devices.apply_to_client(client, raw)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=devices.dingz_id(raw),
        data={CONF_BASE_URL: "http://192.0.2.10"},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.dingz.entity.COMMAND_REFRESH_DELAY", 0):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _unique_ids(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, str]:
    """Map unique id suffix -> entity id."""
    registry = er.async_get(hass)
    prefix = f"{entry.unique_id}_"
    return {
        e.unique_id.removeprefix(prefix): e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }


@pytest.mark.parametrize("name", devices.ALL_DEVICES)
async def test_setup_every_captured_device(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled, name: str
) -> None:
    raw = devices.load(name)
    entry = await _setup(hass, mock_dingz_client, raw)
    ids = _unique_ids(hass, entry)

    # Never a light for an output that is not a controllable dimmer.
    state_absolutes = {
        d["index"]["absolute"]
        for d in raw["state"]["dimmers"]
        if not d.get("readonly", False)
    }
    for suffix in ids:
        if suffix.startswith("output_") and suffix[7:].isdigit():
            assert int(suffix[7:]) in state_absolutes, suffix

    # No sensor that the firmware does not report stays permanently unknown.
    for key in ("cpu_temperature", "puck_temperature"):
        present = raw["state"]["sensors"].get(key) is not None
        assert (f"sensors.{key}" in ids) is present

    for entity_id in ids.values():
        state = hass.states.get(entity_id)
        if state is None:  # disabled by default
            continue
        assert state.state != "unavailable", entity_id


async def test_two_blinds_device_has_no_phantom_lights(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    """DIP 0: output_config lists four active lights, but all drive motors."""
    entry = await _setup(hass, mock_dingz_client, devices.load("fw260_dip0_two_blinds"))
    ids = _unique_ids(hass, entry)

    assert not any(s.startswith("output_") and s[7:].isdigit() for s in ids)
    assert {"cover_0", "cover_1", "front_led"} <= set(ids)
    assert hass.states.get(ids["cover_0"]).name.endswith("Store Diner Ouest Gauche")
    assert hass.states.get(ids["cover_1"]).name.endswith("Store Diner Ouest Droite")
    # 2.6.0 dropped cpu/puck temperatures.
    assert "sensors.cpu_temperature" not in ids
    # MQTT is enabled on the device: energy counters for both motors.
    assert {"energy_motor_0", "energy_motor_1"} <= set(ids)


async def test_cover_uses_config_of_its_absolute_motor(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    """DIP 1: the only motor is absolute motor 1 (relative 0)."""
    entry = await _setup(
        hass, mock_dingz_client, devices.load("fw243_dip1_blind_smartlight")
    )
    ids = _unique_ids(hass, entry)

    # Unique id stays on the relative index used before.
    assert "cover_0" in ids and "cover_1" not in ids
    assert hass.states.get(ids["cover_0"]).name.endswith("Store Cuisine")

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": ids["cover_0"]}, blocking=True
    )
    mock_dingz_client.move_blind.assert_awaited_once_with(0, "up")

    # Firmware 2.4.3 still reports cpu/puck temperatures.
    assert "sensors.cpu_temperature" in ids
    # Outputs 0-1 are smart_light supplies: not exposed as lights.
    assert "output_0" not in ids and "output_1" not in ids


async def test_named_light_and_trimmed_name(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    entry = await _setup(hass, mock_dingz_client, devices.load("fw260_dip1_pir_front"))
    ids = _unique_ids(hass, entry)

    assert "output_0" in ids
    # Configured name is "Miroir " (trailing space).
    assert hass.states.get(ids["output_0"]).name.endswith(" Miroir")
    assert "output_1" not in ids  # smart_light


async def test_power_socket_and_smart_lights(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    entry = await _setup(
        hass, mock_dingz_client, devices.load("fw260_dip3_lights_socket")
    )
    ids = _unique_ids(hass, entry)

    assert "socket_3" in ids
    assert not any(s.startswith("output_") and s[7:].isdigit() for s in ids)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": ids["socket_3"]}, blocking=True
    )
    mock_dingz_client.set_dimmer.assert_awaited_once_with(3, "off")


async def test_input_and_pirs(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    entry = await _setup(hass, mock_dingz_client, devices.load("fw260_dip3_input_pir"))
    ids = _unique_ids(hass, entry)

    assert hass.states.get(ids["input_0"]).state == "on"
    assert {"pir_0", "pir_1"} <= set(ids)
    assert "pir_2" not in ids
    # Output 0 is read-only (used by the input), outputs 2-3 inactive.
    assert "output_0" not in ids
    assert "output_2" not in ids and "output_3" not in ids
    assert hass.states.get(ids["pir_1"]).name.endswith("External PIR motion")


async def test_dimmer_commands_use_relative_index(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    """DIP 2 (motor on outputs 0-1, dimmers on 2-3): relative != absolute."""
    raw = devices.load("fw260_dip3_lights_socket")
    raw["output_config"]["outputs"][2]["type"] = "light"
    raw["output_config"]["outputs"][2]["light"]["dimmable"] = True
    dimmers = raw["state"]["dimmers"]
    raw["state"]["dimmers"] = [
        {**dimmers[2], "index": {"relative": 0, "absolute": 2}},
        {**dimmers[3], "index": {"relative": 1, "absolute": 3}},
    ]
    entry = await _setup(hass, mock_dingz_client, raw)
    ids = _unique_ids(hass, entry)

    assert "output_2" in ids
    assert hass.states.get(ids["output_2"]).name.endswith("Lampes principales")
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": ids["output_2"], "brightness": 1, "transition": 30},
        blocking=True,
    )
    mock_dingz_client.set_dimmer.assert_awaited_once_with(0, "on", value=1, time=10.0)
    # Power is reported per physical output.
    assert hass.states.get(ids["output_power_2"]).state == str(
        raw["state"]["sensors"]["power_outputs"][2]["value"]
    )
