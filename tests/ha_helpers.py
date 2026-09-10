"""Test helpers compatible with Home Assistant 2025.8 ConfigEntry."""

from types import MappingProxyType
from typing import Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class MockConfigEntry(ConfigEntry):
    """ConfigEntry usable in tests against Home Assistant 2025.8+."""

    def __init__(
        self,
        *,
        domain: str,
        data: dict[str, Any],
        unique_id: str | None = None,
        title: str = "Dingz",
        source: str = config_entries.SOURCE_USER,
        version: int = 1,
        minor_version: int = 2,
    ) -> None:
        super().__init__(
            data=data,
            domain=domain,
            unique_id=unique_id,
            title=title,
            source=source,
            version=version,
            minor_version=minor_version,
            discovery_keys=MappingProxyType({}),
            options={},
            subentries_data=(),
        )

    def add_to_hass(self, hass: HomeAssistant) -> None:
        hass.config_entries._entries[self.entry_id] = self
