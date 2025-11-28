"""Data update coordinator for HAC Grades."""
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DEFAULT_SCAN_INTERVAL, DEFAULT_QUARTER, DEFAULT_BROWSERLESS_URL, DOMAIN
from .hac_client import HACClient

_LOGGER = logging.getLogger(__name__)


class HACDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching HAC data."""

    def __init__(
        self,
        hass: HomeAssistant,
        school_url: str,
        username: str,
        password: str,
        student_id: str,
        quarter: str = DEFAULT_QUARTER,
        scan_interval: timedelta = DEFAULT_SCAN_INTERVAL,
        browserless_url: str = DEFAULT_BROWSERLESS_URL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=scan_interval,
        )
        self.school_url = school_url
        self.username = username
        self.password = password
        self.student_id = student_id
        self.quarter = quarter
        self.browserless_url = browserless_url
        self._session: aiohttp.ClientSession | None = None
        self._client: HACClient | None = None

    def _ensure_timezone_aware(self, data: dict[str, Any]) -> dict[str, Any]:
        """Ensure last_updated timestamp has timezone info."""
        if "last_updated" in data:
            last_updated = data["last_updated"]

            # If it's a datetime object without timezone, add UTC
            if isinstance(last_updated, datetime) and last_updated.tzinfo is None:
                _LOGGER.warning("Fixing naive datetime in coordinator data, adding UTC timezone")
                data["last_updated"] = dt_util.as_utc(last_updated)
            # If it's a string, parse and ensure timezone
            elif isinstance(last_updated, str):
                try:
                    parsed = dt_util.parse_datetime(last_updated)
                    if parsed and parsed.tzinfo is None:
                        _LOGGER.warning("Fixing parsed naive datetime in coordinator data, adding UTC timezone")
                        data["last_updated"] = dt_util.as_utc(parsed)
                    elif parsed:
                        data["last_updated"] = parsed
                except (ValueError, TypeError):
                    _LOGGER.error("Could not parse last_updated string: %s", last_updated)

        return data

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from HAC."""
        try:
            # Create session if needed
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession()

            # Create client if needed
            if self._client is None:
                self._client = HACClient(
                    self.school_url,
                    self.username,
                    self.password,
                    self._session,
                    student_id=self.student_id,
                    browserless_url=self.browserless_url,
                )

            # Fetch grades for all quarters
            data = await self._client.fetch_grades()

            # Ensure timezone is present (handles both new and cached data)
            data = self._ensure_timezone_aware(data)

            if "error" in data:
                raise UpdateFailed(f"Error fetching data: {data['error']}")

            # Extract the specific quarter's data
            quarters_data = data.get("quarters", {})
            quarter_data = quarters_data.get(self.quarter)

            if not quarter_data:
                _LOGGER.warning(
                    "No data found for quarter %s. Available quarters: %s",
                    self.quarter,
                    list(quarters_data.keys())
                )
                # Return empty structure if quarter not found
                return {
                    "courses": [],
                    "overall_summary": {
                        "course_count": 0,
                        "gpa_like_average": None,
                        "weighted_gpa_like_average": None,
                        "latest_update_date": None,
                        "days_since_latest_update": None,
                    },
                    "last_updated": data.get("last_updated"),
                    "student_id": data.get("student_id"),
                    "quarter": self.quarter,
                }

            # Flatten the quarter data to root level for sensors
            flattened_data = {
                "courses": quarter_data.get("courses", []),
                "overall_summary": quarter_data.get("overall_summary", {}),
                "last_updated": data.get("last_updated"),
                "student_id": data.get("student_id"),
                "quarter": self.quarter,
                "all_quarters": quarters_data,  # Keep all quarters for reference
            }

            _LOGGER.info(
                "Successfully updated HAC data for %s: %d courses",
                self.quarter,
                len(flattened_data["courses"])
            )

            return flattened_data

        except Exception as err:
            _LOGGER.error("Error updating HAC data: %s", err)
            raise UpdateFailed(f"Error updating HAC data: {err}") from err

    async def async_shutdown(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
