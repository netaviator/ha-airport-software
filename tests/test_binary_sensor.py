from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.airport_software.const import DOMAIN
from custom_components.airport_software.models import AircraftStatus

BASE_ENTRY_DATA = {
    "base_url": "https://example.test",
    "username": "1234",
    "password": "secret",
    "enable_tower_duty": False,
    "enable_qualification_status": False,
}


async def test_in_use_binary_sensor_reflects_status(hass):
    status = AircraftStatus(
        tail_number="D-ABCD",
        in_use=True,
        condition="ready",
        open_info_count=0,
        remaining_hours=1.0,
        remarks="",
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**BASE_ENTRY_DATA, "enable_free_rest_of_day": True, "free_rest_of_day_cutoff": "18:00"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_status",
        return_value=[status],
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.d_abcd_in_use")
    assert state is not None
    assert state.state == "on"


async def test_free_rest_of_day_binary_sensor_created_when_enabled(hass):
    status = AircraftStatus(
        tail_number="D-ABCD",
        in_use=False,
        condition="ready",
        open_info_count=0,
        remaining_hours=1.0,
        remarks="",
        available_from_today="immediate",
        free_rest_of_day=True,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**BASE_ENTRY_DATA, "enable_free_rest_of_day": True, "free_rest_of_day_cutoff": "18:00"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_status",
        return_value=[status],
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.d_abcd_free_rest_of_day")
    assert state is not None
    assert state.state == "on"
    assert state.attributes["available_from"] == "immediate"


async def test_free_rest_of_day_binary_sensor_absent_when_disabled(hass):
    status = AircraftStatus(
        tail_number="D-ABCD",
        in_use=False,
        condition="ready",
        open_info_count=0,
        remaining_hours=1.0,
        remarks="",
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**BASE_ENTRY_DATA, "enable_free_rest_of_day": False, "free_rest_of_day_cutoff": "18:00"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_status",
        return_value=[status],
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.d_abcd_free_rest_of_day") is None
