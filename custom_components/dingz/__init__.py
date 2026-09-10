"""The Dingz integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue

from .const import DOMAIN
from .coordinator import DingzConfigEntry, DingzRuntime

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.EVENT,
    Platform.FAN,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]


async def async_setup_entry(hass: HomeAssistant, entry: DingzConfigEntry) -> bool:
    runtime = DingzRuntime(hass, entry)
    await runtime.async_setup()
    entry.runtime_data = runtime

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DingzConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_unload()
    return unload_ok


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: DingzConfigEntry
) -> bool:
    """Migrate old entry."""
    version = (config_entry.version, config_entry.minor_version)

    if version == (1, 1):
        async_create_issue(
            hass,
            DOMAIN,
            f"output_energy_dropped_{config_entry.entry_id}",
            is_fixable=False,
            is_persistent=True,
            severity=IssueSeverity.WARNING,
            translation_key="output_energy_dropped",
        )

    return True
