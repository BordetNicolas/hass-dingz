"""Platform behaviour through Home Assistant with captured payloads."""

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    mock_restore_cache_with_extra_data,
)

from custom_components.dingz.const import CONF_BASE_URL, DOMAIN
from custom_components.dingz.diagnostics import async_get_config_entry_diagnostics
from custom_components.dingz.models import (
    ButtonNotification,
    EnergyNotification,
    MqttOnlineNotification,
    PirNotification,
)
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


def _entity(hass: HomeAssistant, entry: MockConfigEntry, suffix: str) -> str:
    registry = er.async_get(hass)
    for e in er.async_entries_for_config_entry(registry, entry.entry_id):
        if e.unique_id == f"{entry.unique_id}_{suffix}":
            return e.entity_id
    raise AssertionError(suffix)


async def test_diagnostics_are_redacted(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    raw = devices.load("fw260_dip0_two_blinds")
    raw["services_config"]["mqtt"]["uri"] = "mqtt://user:secret@broker"
    entry = await _setup(hass, mock_dingz_client, raw)

    diag = await async_get_config_entry_diagnostics(hass, entry)
    dumped = json.dumps(diag)
    assert "secret" not in dumped
    assert raw["state"]["wifi"]["mac"] not in dumped
    assert raw["state"]["wifi"]["ip"] not in dumped
    assert diag["firmware"] == {"version": "2.6.0", "supported": True}
    assert diag["capabilities"]["mqtt_enabled"] is True
    assert [b["absolute"] for b in diag["capabilities"]["blinds"]] == [0, 1]


async def test_energy_sensor_restore_and_push(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    raw = devices.load("fw260_dip0_two_blinds")
    entry = await _setup(hass, mock_dingz_client, raw)
    entity_id = _entity(hass, entry, "energy_motor_0")
    # Firmware publishes watt-seconds; shown in kWh.
    assert hass.states.get(entity_id).attributes["unit_of_measurement"] == "kWh"

    runtime = entry.runtime_data
    runtime.dispatch(EnergyNotification(kind="motor", index=0, value=36_000_000.0))
    runtime.dispatch(EnergyNotification(kind="light", index=0, value=1.0))
    await hass.async_block_till_done()
    assert float(hass.states.get(entity_id).state) == pytest.approx(10.0)

    # After a restart, the last counter value is restored before MQTT speaks.
    assert await hass.config_entries.async_unload(entry.entry_id)
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(entity_id, "0.005"),
                {"native_value": 18000.0, "native_unit_of_measurement": "J"},
            )
        ],
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert float(hass.states.get(entity_id).state) == pytest.approx(0.005)


async def test_events_and_mqtt_online(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    entry = await _setup(hass, mock_dingz_client, devices.load("fw260_dip3_input_pir"))
    runtime = entry.runtime_data
    button = _entity(hass, entry, "button_0")
    pir = _entity(hass, entry, "pir_event_0")
    online = _entity(hass, entry, "mqtt_online")

    runtime.dispatch(ButtonNotification(index=0, event_type="m2"))
    runtime.dispatch(ButtonNotification(index=0, event_type="m9"))  # unknown
    runtime.dispatch(PirNotification(index=0, event_type="s"))
    runtime.dispatch(MqttOnlineNotification(online=True))
    await hass.async_block_till_done()

    assert hass.states.get(button).attributes["event_type"] == "m2"
    assert hass.states.get(pir).attributes["event_type"] == "s"
    assert hass.states.get(online).state == "on"


async def test_structure_change_reloads_entry(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    raw = devices.load("fw260_dip3_lights_socket")
    entry = await _setup(hass, mock_dingz_client, raw)
    coordinator = entry.runtime_data.coordinator

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        await coordinator.async_refresh()
        reload.assert_not_called()

        changed = devices.load("fw260_dip3_lights_socket")
        changed["state"]["sensors"]["pirs"][1]["enabled"] = True
        mock_dingz_client.get_state.return_value = changed["state"]
        await coordinator.async_refresh()
        reload.assert_called_once_with(entry.entry_id)


async def test_old_firmware_creates_issue(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    raw = devices.load("fw243_dip1_blind_smartlight")
    next(iter(raw["device"].values()))["fw_version"] = "1.3.30"
    entry = await _setup(hass, mock_dingz_client, raw)
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"unsupported_firmware_{entry.entry_id}"
    )
    assert issue is not None
    assert issue.translation_placeholders["version"] == "1.3.30"


async def test_setup_retries_when_unreachable(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    mock_dingz_client.get_full_device_config.side_effect = TimeoutError
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="x", data={CONF_BASE_URL: "http://192.0.2.10"}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_auth_required_is_reported(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    mock_dingz_client.get_state.side_effect = aiohttp.ClientResponseError(
        request_info=MagicMock(), history=(), status=401
    )
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="x", data={CONF_BASE_URL: "http://192.0.2.10"}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.reason.startswith("The dingz refused access (HTTP 401/403)")


async def test_command_failure_raises_translated_error(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    entry = await _setup(hass, mock_dingz_client, devices.load("fw260_dip1_pir_front"))
    light = _entity(hass, entry, "output_0")
    mock_dingz_client.set_dimmer.side_effect = aiohttp.ClientConnectionError("down")
    with pytest.raises(HomeAssistantError) as exc:
        await hass.services.async_call(
            "light", "turn_on", {"entity_id": light}, blocking=True
        )
    assert exc.value.translation_key == "command_failed"

    mock_dingz_client.set_dimmer.side_effect = TimeoutError
    with pytest.raises(HomeAssistantError) as exc:
        await hass.services.async_call(
            "light", "turn_off", {"entity_id": light}, blocking=True
        )
    assert exc.value.translation_key == "command_timeout"


async def test_buttons_follow_device_availability(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    entry = await _setup(hass, mock_dingz_client, devices.load("fw260_dip3_input_pir"))
    reboot = _entity(hass, entry, "reboot")
    await hass.services.async_call(
        "button", "press", {"entity_id": reboot}, blocking=True
    )
    mock_dingz_client.reboot.assert_awaited_once()

    mock_dingz_client.get_state.side_effect = TimeoutError
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(reboot).state == "unavailable"


async def test_mqtt_uri_password_is_masked(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    raw = devices.load("fw260_dip3_input_pir")
    raw["services_config"]["mqtt"]["uri"] = "mqtt://dingz:s3cret@192.0.2.5:1883"
    entry = await _setup(hass, mock_dingz_client, raw)
    text = _entity(hass, entry, "mqtt_uri")
    assert hass.states.get(text).state == "mqtt://dingz:********@192.0.2.5:1883"

    # Editing the host without retyping the password keeps the stored one.
    await hass.services.async_call(
        "text",
        "set_value",
        {"entity_id": text, "value": "mqtt://dingz:********@192.0.2.6:1883"},
        blocking=True,
    )
    sent = mock_dingz_client.update_mqtt_service_config.await_args.args[0]
    assert sent["uri"] == "mqtt://dingz:s3cret@192.0.2.6:1883"
    assert sent["enable"] is True


async def test_unload_unsubscribes_mqtt(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    unsub = MagicMock()
    with patch(
        "custom_components.dingz.mqtt.async_setup_mqtt", AsyncMock(return_value=unsub)
    ):
        entry = await _setup(
            hass, mock_dingz_client, devices.load("fw260_dip3_input_pir")
        )
    assert await hass.config_entries.async_unload(entry.entry_id)
    unsub.assert_called_once()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_thermostat(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    raw = devices.load("fw243_dip1_blind_smartlight")
    raw["state"]["thermostat"].update(
        active=True, enabled=True, mode="heating", state="heating", temp=20.5
    )
    entry = await _setup(hass, mock_dingz_client, raw)
    climate = _entity(hass, entry, "climate")
    state = hass.states.get(climate)
    assert state.state == "heat"
    assert state.attributes["current_temperature"] == 20.5
    assert state.attributes["temperature"] == 21
    assert state.attributes["hvac_action"] == "heating"
    assert state.attributes["min_temp"] == 17

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": climate, "hvac_mode": "cool"},
        blocking=True,
    )
    mock_dingz_client.set_thermostat_mode.assert_awaited_once_with("cooling")
    mock_dingz_client.set_thermostat.assert_awaited_with(enable=True)

    await hass.services.async_call(
        "climate", "turn_off", {"entity_id": climate}, blocking=True
    )
    mock_dingz_client.set_thermostat.assert_awaited_with(enable=False)

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": climate, "temperature": 23},
        blocking=True,
    )
    mock_dingz_client.set_thermostat.assert_awaited_with(target_temp=23)
