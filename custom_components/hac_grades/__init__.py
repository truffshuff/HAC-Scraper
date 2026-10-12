"""The HAC Grades integration."""
from datetime import timedelta
import inspect
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_DRY_RUN,
    CONF_SCHOOL_URL,
    CONF_STUDENT_ID,
    CONF_QUARTER,
    CONF_BROWSERLESS_URL,
    DATA_COORDINATOR,
    DATA_ENTITY_QUARTERS,
    DATA_UNIQUE_IDS,
    DATA_VIA_DEVICE,
    DEFAULT_QUARTER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_BROWSERLESS_URL,
    DOMAIN,
    QUARTERS,
    SERVICE_REMOVE_STALE_ENTITIES,
)
from .coordinator import HACDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

REMOVE_STALE_SCHEMA = vol.Schema({vol.Optional(ATTR_DRY_RUN, default=False): cv.boolean})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions."""

    async def _remove_stale_entities(call: ServiceCall) -> ServiceResponse:
        return {
            "entries": [
                _remove_stale_for_entry(hass, entry, call.data[ATTR_DRY_RUN])
                for entry in hass.config_entries.async_entries(DOMAIN)
                if entry.state is ConfigEntryState.LOADED
            ]
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_STALE_ENTITIES,
        _remove_stale_entities,
        schema=REMOVE_STALE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


def _remove_stale_for_entry(hass: HomeAssistant, entry: ConfigEntry, dry_run: bool) -> dict:
    """Remove a student's entities and course devices that no longer exist in HAC.

    Stale means registered to this config entry but not created this run, e.g.
    last year's courses, which otherwise linger as "unavailable" forever.
    Entities are only created for quarters fetched successfully at startup, so
    this refuses to run unless all quarters loaded; otherwise a failed scrape
    would make that quarter's real entities look stale.
    """
    result: dict = {"title": entry.title, "removed_entities": [], "removed_devices": [], "skipped": None}
    data = hass.data[DOMAIN][entry.entry_id]
    quarters = data[DATA_ENTITY_QUARTERS]

    if quarters is None:
        result["skipped"] = "Entities are still being created; try again once the first refresh finishes"
        return result
    missing = [q for q in QUARTERS if q not in quarters]
    if missing:
        result["skipped"] = (
            f"{', '.join(missing)} failed to load at startup; reload the integration "
            "or restart Home Assistant and try again"
        )
        return result

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    current = data[DATA_UNIQUE_IDS]

    for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if entity.unique_id not in current:
            result["removed_entities"].append(entity.entity_id)
            if not dry_run:
                ent_reg.async_remove(entity.entity_id)

    removed = set(result["removed_entities"])
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if (DOMAIN, entry.entry_id) in device.identifiers:
            continue  # the student device
        remaining = [
            e for e in er.async_entries_for_device(ent_reg, device.id, include_disabled_entities=True)
            if e.entity_id not in removed
        ]
        if not remaining:
            result["removed_devices"].append(device.name_by_user or device.name)
            if not dry_run:
                dev_reg.async_remove_device(device.id)

    _LOGGER.info(
        "%s stale entities for %s: %d entities, %d devices",
        "Found" if dry_run else "Removed",
        entry.title,
        len(result["removed_entities"]),
        len(result["removed_devices"]),
    )
    return result


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
        DATA_UNIQUE_IDS: set(),
        DATA_ENTITY_QUARTERS: None,
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
