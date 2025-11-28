"""Config flow for HAC Grades integration."""
from typing import Any
import logging

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_SCHOOL_URL,
    CONF_STUDENT_ID,
    CONF_QUARTER,
    CONF_BROWSERLESS_URL,
    DEFAULT_QUARTER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_BROWSERLESS_URL,
    DOMAIN,
    QUARTERS,
)
from .hac_client import HACClient

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_STUDENT_ID): str,
        vol.Required(CONF_SCHOOL_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_BROWSERLESS_URL, default=DEFAULT_BROWSERLESS_URL): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = aiohttp.ClientSession()
    try:
        client = HACClient(
            data[CONF_SCHOOL_URL],
            data[CONF_USERNAME],
            data[CONF_PASSWORD],
            session,
            student_id=data[CONF_STUDENT_ID],
            browserless_url=data.get(CONF_BROWSERLESS_URL, DEFAULT_BROWSERLESS_URL),
        )

        # Try to login only - this is fast and validates credentials
        # Don't fetch all quarters here as it takes 2-3 minutes with staggered requests
        if not await client.login():
            raise ValueError("Invalid credentials or unable to login")

        # Validate student ID from the login page
        detected_id = client._detected_student_id
        if detected_id and detected_id != data[CONF_STUDENT_ID]:
            raise ValueError(f"Student ID mismatch. Expected {data[CONF_STUDENT_ID]}, found {detected_id}")

        # Return info that you want to store in the config entry.
        # Note: Full grade fetching will happen after setup is complete via the coordinator
        return {
            "title": f"HAC - Student {data[CONF_STUDENT_ID]}",
        }

    finally:
        await session.close()


class HACGradesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HAC Grades."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except ValueError as err:
                _LOGGER.error("Validation failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during config flow validation: %s", err)
                errors["base"] = "unknown"
            else:
                # Create unique ID based on school URL and student ID
                await self.async_set_unique_id(
                    f"{user_input[CONF_SCHOOL_URL]}_{user_input[CONF_STUDENT_ID]}"
                )
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return HACGradesOptionsFlowHandler(config_entry)


class HACGradesOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for HAC Grades."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL,
                            int(DEFAULT_SCAN_INTERVAL.total_seconds() / 3600),
                        ),
                    ): vol.In({
                        1: "1 hour",
                        2: "2 hours",
                        3: "3 hours",
                        4: "4 hours",
                        6: "6 hours (recommended)",
                        8: "8 hours",
                        12: "12 hours",
                        24: "24 hours",
                    }),
                }
            ),
        )
