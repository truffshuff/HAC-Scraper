"""The HAC Grades integration."""
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_SCHOOL_URL,
    CONF_STUDENT_ID,
    CONF_QUARTER,
    CONF_BROWSERLESS_URL,
    DATA_COORDINATOR,
    DEFAULT_QUARTER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_BROWSERLESS_URL,
    DOMAIN,
)
from .coordinator import HACDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HAC Grades from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Get scan interval from options, or use default
    scan_interval_hours = entry.options.get(
        CONF_SCAN_INTERVAL,
        int(DEFAULT_SCAN_INTERVAL.total_seconds() / 3600),
    )
    scan_interval = timedelta(hours=scan_interval_hours)

    # Get quarter from config, or use default
    quarter = entry.data.get(CONF_QUARTER, DEFAULT_QUARTER)

    # Get browserless URL from config, or use default
    browserless_url = entry.data.get(CONF_BROWSERLESS_URL, DEFAULT_BROWSERLESS_URL)

    # Create coordinator
    coordinator = HACDataUpdateCoordinator(
        hass,
        entry.data[CONF_SCHOOL_URL],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_STUDENT_ID],
        quarter,
        scan_interval,
        browserless_url,
    )

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
    }

    # Trigger the initial data fetch in the background first
    # Note: This will take 2-3 minutes due to staggered requests across quarters
    _LOGGER.info(
        "Starting initial data fetch in background. "
        "This may take 2-3 minutes due to staggered requests across quarters. "
        "Setup will complete immediately and sensors will be created once data is available."
    )

    # Schedule the first refresh (non-blocking)
    hass.async_create_task(coordinator.async_request_refresh())

    # Setup platforms (this will wait for data in the background)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Setup options update listener
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
        await coordinator.async_shutdown()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
