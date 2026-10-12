"""The HAC Grades integration."""
from datetime import timedelta
import inspect
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_SCHOOL_URL,
    CONF_STUDENT_ID,
    CONF_QUARTER,
    CONF_BROWSERLESS_URL,
    DATA_COORDINATOR,
    DATA_VIA_DEVICE,
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

    # Create the student (parent) device up front so per-course devices can
    # link to it by registry ID. HA deprecated linking by identifier tuple
    # (`via_device`) in favor of `via_device_id`, removal in 2027.8.
    student_id = entry.data[CONF_STUDENT_ID]
    student_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"HAC - Student {student_id}",
        manufacturer="Home Access Center",
        model="Grade Portal",
    )

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_VIA_DEVICE: _via_device_kwargs(student_device.id, entry.entry_id),
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


def _via_device_kwargs(device_id: str, entry_id: str) -> dict:
    """Return the DeviceInfo key linking a course device to the student device.

    Uses `via_device_id` where supported, falling back to the identifier tuple
    on cores that predate it.
    """
    params = inspect.signature(dr.DeviceRegistry.async_get_or_create).parameters
    if "via_device_id" in params:
        return {"via_device_id": device_id}
    return {"via_device": (DOMAIN, entry_id)}


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
