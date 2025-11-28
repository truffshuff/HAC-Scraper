"""Button platform for HAC Grades."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STUDENT_ID, DATA_COORDINATOR, DOMAIN
from .coordinator import HACDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HAC Grades button entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    student_id = entry.data[CONF_STUDENT_ID]

    async_add_entities([HACRefreshButton(coordinator, entry, student_id)])


class HACRefreshButton(CoordinatorEntity[HACDataUpdateCoordinator], ButtonEntity):
    """Button to force refresh HAC data."""

    def __init__(
        self,
        coordinator: HACDataUpdateCoordinator,
        entry: ConfigEntry,
        student_id: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._student_id = student_id
        self._entry = entry
        self._attr_name = "Force Refresh"
        self._attr_unique_id = f"{entry.entry_id}_force_refresh"
        self._attr_icon = "mdi:refresh"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"HAC - Student {self._student_id}",
            "manufacturer": "Home Access Center",
            "model": "Grade Portal",
        }

    async def async_press(self) -> None:
        """Handle button press - force a data refresh."""
        _LOGGER.info("Force refresh triggered for student %s", self._student_id)
        await self.coordinator.async_request_refresh()
