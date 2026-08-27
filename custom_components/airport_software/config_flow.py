"""Config flow for airport-software."""
from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .client import AirportSoftwareClient, InvalidAuth
from .const import (
    CONF_BASE_URL,
    CONF_ENABLE_FREE_REST_OF_DAY,
    CONF_ENABLE_QUALIFICATION_STATUS,
    CONF_ENABLE_TOWER_DUTY,
    CONF_FREE_REST_OF_DAY_CUTOFF,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_FREE_REST_OF_DAY_CUTOFF,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
_CUTOFF_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _validate_cutoff(value: str) -> str:
    if not _CUTOFF_TIME_RE.match(value):
        raise vol.Invalid("invalid time format, expected HH:MM")
    return value


# NOTE: the cutoff field intentionally uses plain `str` here, not
# `_validate_cutoff`, even though this schema is also passed as the form's
# `data_schema`. Home Assistant's FlowManager.async_configure() re-applies
# the *current* step's data_schema to resubmitted input itself, before ever
# calling back into async_step_user() (see
# homeassistant/data_entry_flow.py, FlowManager.async_configure), and lets
# any vol.Invalid raised there propagate uncaught as InvalidData rather than
# routing it back to the step handler. That would turn a malformed cutoff
# into an unhandled exception instead of the FORM/"invalid_cutoff_format"
# result the config flow is supposed to show. So format validation is done
# explicitly inside async_step_user() instead (see below), where it can be
# caught and turned into a proper form error; the schema here only supplies
# type coercion and defaults.
STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_ENABLE_FREE_REST_OF_DAY, default=True): bool,
        vol.Optional(
            CONF_FREE_REST_OF_DAY_CUTOFF, default=DEFAULT_FREE_REST_OF_DAY_CUTOFF
        ): str,
        vol.Optional(CONF_ENABLE_TOWER_DUTY, default=True): bool,
        vol.Optional(CONF_ENABLE_QUALIFICATION_STATUS, default=True): bool,
    }
)


async def _async_validate(data: dict[str, Any]) -> None:
    """Raise InvalidAuth or ConnectionError if the credentials don't work."""
    async with aiohttp.ClientSession() as session:
        client = AirportSoftwareClient(
            session,
            data[CONF_BASE_URL],
            data[CONF_USERNAME],
            data[CONF_PASSWORD],
            enable_free_rest_of_day=data[CONF_ENABLE_FREE_REST_OF_DAY],
            free_rest_of_day_cutoff=data[CONF_FREE_REST_OF_DAY_CUTOFF],
        )
        await client.async_get_status()


class AirportSoftwareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                _validate_cutoff(user_input[CONF_FREE_REST_OF_DAY_CUTOFF])
            except vol.Invalid:
                errors["base"] = "invalid_cutoff_format"
            else:
                try:
                    await _async_validate(user_input)
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except Exception:  # noqa: BLE001 - anything else is "can't connect"
                    _LOGGER.exception("Unexpected error validating airport-software login")
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=user_input[CONF_BASE_URL], data=user_input
                    )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        self._reauth_entry_data = entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            new_data = {**self._reauth_entry_data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            try:
                await _async_validate(new_data)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating airport-software login")
                errors["base"] = "cannot_connect"
            else:
                existing_entry = self.hass.config_entries.async_get_entry(
                    self.context["entry_id"]
                )
                self.hass.config_entries.async_update_entry(existing_entry, data=new_data)
                await self.hass.config_entries.async_reload(existing_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )
