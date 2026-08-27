from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.airport_software.const import DOMAIN
from custom_components.airport_software.models import AircraftStatus

ENTRY_DATA = {
    "base_url": "https://example.test",
    "username": "1234",
    "password": "secret",
    "enable_free_rest_of_day": True,
    "free_rest_of_day_cutoff": "18:00",
    "enable_tower_duty": True,
    "enable_qualification_status": True,
}


async def test_setup_entry_creates_coordinator_and_fetches_data(hass):
    status = AircraftStatus(
        tail_number="D-ABCD",
        in_use=False,
        condition="ready",
        open_info_count=0,
        remaining_hours=1.0,
        remarks="",
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

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    assert coordinator.data == {"D-ABCD": status}
    assert hass.data[DOMAIN][entry.entry_id]["tower_duty_coordinator"] is not None
    assert hass.data[DOMAIN][entry.entry_id]["qualification_coordinator"] is not None


async def test_setup_entry_skips_optional_coordinators_when_disabled(hass):
    entry_data = {
        **ENTRY_DATA,
        "enable_tower_duty": False,
        "enable_qualification_status": False,
    }
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_status",
        return_value=[],
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.data[DOMAIN][entry.entry_id]["tower_duty_coordinator"] is None
    assert hass.data[DOMAIN][entry.entry_id]["qualification_coordinator"] is None


async def test_setup_entry_succeeds_when_optional_tower_duty_fetch_fails(hass):
    status = AircraftStatus(
        tail_number="D-ABCD",
        in_use=False,
        condition="ready",
        open_info_count=0,
        remaining_hours=1.0,
        remarks="",
    )
    entry = MockConfigEntry(
        domain=DOMAIN, data={**ENTRY_DATA, "enable_qualification_status": False}
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_status",
        return_value=[status],
    ), patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_tower_duty",
        side_effect=ConnectionError("boom"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Aircraft data still loaded fine despite the tower duty fetch failing.
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    assert coordinator.data == {"D-ABCD": status}


async def test_unload_entry_closes_session(hass):
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
        return_value=None,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    session = hass.data[DOMAIN][entry.entry_id]["session"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert session.closed
