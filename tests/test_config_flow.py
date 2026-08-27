from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.airport_software.client import InvalidAuth
from custom_components.airport_software.const import (
    CONF_ENABLE_FREE_REST_OF_DAY,
    CONF_ENABLE_QUALIFICATION_STATUS,
    CONF_ENABLE_TOWER_DUTY,
    CONF_FREE_REST_OF_DAY_CUTOFF,
    CONF_PASSWORD,
    DOMAIN,
)

REQUIRED_INPUT = {
    "base_url": "https://example.test",
    "username": "1234",
    "password": "secret",
}

REAUTH_ENTRY_DATA = {
    "base_url": "https://example.test",
    "username": "1234",
    "password": "old-secret",
    "enable_free_rest_of_day": True,
    "free_rest_of_day_cutoff": "18:00",
    # Disabled so a reauth-triggered reload only sets up the required
    # coordinator (patched below) and doesn't also need real network
    # access for the optional tower-duty/qualification coordinators.
    "enable_tower_duty": False,
    "enable_qualification_status": False,
}


async def test_user_flow_creates_entry_with_flynow_defaults(hass):
    with patch(
        "custom_components.airport_software.config_flow.AirportSoftwareClient.async_get_status",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], REQUIRED_INPUT
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ENABLE_FREE_REST_OF_DAY] is True
    assert result["data"][CONF_FREE_REST_OF_DAY_CUTOFF] == "18:00"
    assert result["data"][CONF_ENABLE_TOWER_DUTY] is True
    assert result["data"][CONF_ENABLE_QUALIFICATION_STATUS] is True


async def test_user_flow_accepts_explicit_flynow_settings(hass):
    user_input = {
        **REQUIRED_INPUT,
        "enable_free_rest_of_day": False,
        "free_rest_of_day_cutoff": "20:00",
        "enable_tower_duty": False,
        "enable_qualification_status": False,
    }
    with patch(
        "custom_components.airport_software.config_flow.AirportSoftwareClient.async_get_status",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ENABLE_FREE_REST_OF_DAY] is False
    assert result["data"][CONF_FREE_REST_OF_DAY_CUTOFF] == "20:00"
    assert result["data"][CONF_ENABLE_TOWER_DUTY] is False
    assert result["data"][CONF_ENABLE_QUALIFICATION_STATUS] is False


async def test_user_flow_rejects_malformed_cutoff(hass):
    user_input = {**REQUIRED_INPUT, "free_rest_of_day_cutoff": "not-a-time"}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_cutoff_format"}


async def test_user_flow_shows_invalid_auth_error(hass):
    with patch(
        "custom_components.airport_software.config_flow.AirportSoftwareClient.async_get_status",
        side_effect=InvalidAuth("bad password"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], REQUIRED_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_shows_cannot_connect_error(hass):
    with patch(
        "custom_components.airport_software.config_flow.AirportSoftwareClient.async_get_status",
        side_effect=ConnectionError("boom"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], REQUIRED_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_flow_updates_password_on_success(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=REAUTH_ENTRY_DATA)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.airport_software.config_flow.AirportSoftwareClient.async_get_status",
        return_value=[],
    ):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "new-secret"}
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-secret"


async def test_reauth_flow_shows_invalid_auth_error(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=REAUTH_ENTRY_DATA)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.airport_software.config_flow.AirportSoftwareClient.async_get_status",
        side_effect=InvalidAuth("bad password"),
    ):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "still-wrong"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[CONF_PASSWORD] == "old-secret"
