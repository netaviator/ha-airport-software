from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.airport_software.const import DOMAIN
from custom_components.airport_software.models import AircraftStatus, QualificationStatus, TowerDutyStatus

ENTRY_DATA = {
    "base_url": "https://example.test",
    "username": "1234",
    "password": "secret",
    "enable_free_rest_of_day": True,
    "free_rest_of_day_cutoff": "18:00",
    "enable_tower_duty": True,
    "enable_qualification_status": True,
}


async def test_condition_sensor_reports_state_and_attributes(hass):
    status = AircraftStatus(
        tail_number="D-ABCD",
        in_use=False,
        condition="maintenance",
        open_info_count=2,
        remaining_hours=-1.5,
        remarks="Engine work.",
    )
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_status",
        return_value=[status],
    ), patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_tower_duty",
        return_value=None,
    ), patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_next_expiring_qualification",
        return_value=None,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    condition_state = hass.states.get("sensor.d_abcd_condition")
    assert condition_state.state == "maintenance"
    assert condition_state.attributes["open_info_count"] == 2
    assert condition_state.attributes["remarks"] == "Engine work."

    hours_state = hass.states.get("sensor.d_abcd_remaining_hours")
    assert hours_state.state == "-1.5"


async def test_tower_duty_sensor_created_when_enabled(hass):
    duty = TowerDutyStatus(on_duty="Rey, Elena", note=None)
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_status",
        return_value=[],
    ), patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_tower_duty",
        return_value=duty,
    ), patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_next_expiring_qualification",
        return_value=None,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.tower_duty_now")
    assert state is not None
    assert state.state == "Rey, Elena"


async def test_tower_duty_sensor_absent_when_disabled(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={**ENTRY_DATA, "enable_tower_duty": False}
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_status",
        return_value=[],
    ), patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_next_expiring_qualification",
        return_value=None,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get("sensor.tower_duty_now") is None


async def test_qualification_sensor_absent_when_disabled(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={**ENTRY_DATA, "enable_qualification_status": False}
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_status",
        return_value=[],
    ), patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_tower_duty",
        return_value=None,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get("sensor.next_expiring_qualification") is None


async def test_qualification_sensor_reports_days_remaining_and_severity(hass):
    qualification = QualificationStatus(
        label="Medical Class II",
        subcode="MEDICAL - CLASS II",
        end_date="2026-09-10",
        days_remaining=10,
        severity="warning",
    )
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_status",
        return_value=[],
    ), patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_tower_duty",
        return_value=None,
    ), patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_next_expiring_qualification",
        return_value=qualification,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.next_expiring_qualification")
    assert state is not None
    assert state.state == "10"
    assert state.attributes["label"] == "Medical Class II"
    assert state.attributes["severity"] == "warning"
