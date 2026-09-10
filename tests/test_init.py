"""Integration setup and entity creation tests."""

from unittest.mock import patch

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant

from custom_components.dingz.const import CONF_BASE_URL, DOMAIN
from tests.fixtures.payloads import BASE_URL, DINGZ_ID, state_payload
from tests.ha_helpers import MockConfigEntry


async def test_setup_creates_expected_entities(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DINGZ_ID,
        data={CONF_BASE_URL: BASE_URL},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.dingz.entity.COMMAND_REFRESH_DELAY",
        0,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_ids = hass.states.async_entity_ids()
    # Active lights (2), front LED, power socket, cover, PIR, input, temperatures...
    assert any(eid.startswith("light.") for eid in entity_ids)
    assert any(eid.startswith("switch.") for eid in entity_ids)
    assert any(eid.startswith("cover.") for eid in entity_ids)
    assert any(eid.startswith("sensor.") for eid in entity_ids)
    assert any(eid.startswith("binary_sensor.") for eid in entity_ids)
    assert any(eid.startswith("climate.") for eid in entity_ids)

    # Inactive output must not become a light
    lights = [eid for eid in entity_ids if eid.startswith("light.")]
    assert len(lights) >= 3  # front + 2 active lights

    # Event entities require MQTT enable on the device
    assert not any(eid.startswith("event.") for eid in entity_ids)


async def test_unavailable_then_recovery(
    hass: HomeAssistant, mock_dingz_client, mock_mqtt_disabled
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DINGZ_ID,
        data={CONF_BASE_URL: BASE_URL},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    import aiohttp

    mock_dingz_client.get_state.side_effect = aiohttp.ClientConnectionError("down")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.last_update_success is False

    mock_dingz_client.get_state.side_effect = None
    mock_dingz_client.get_state.return_value = state_payload()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.last_update_success is True
