import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.airport_software.client import InvalidAuth
from custom_components.airport_software.coordinator import AirportSoftwareCoordinator
from custom_components.airport_software.models import AircraftStatus


class _FakeClient:
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc
        self.calls = 0

    async def async_get_status(self):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return self._result


async def test_update_data_returns_statuses_keyed_by_tail_number(hass):
    status = AircraftStatus(
        tail_number="D-ABCD",
        in_use=False,
        condition="ready",
        open_info_count=0,
        remaining_hours=1.0,
        remarks="",
    )
    client = _FakeClient(result=[status])
    coordinator = AirportSoftwareCoordinator(hass, entry=None, client=client)

    data = await coordinator._async_update_data()

    assert data == {"D-ABCD": status}


async def test_update_data_raises_config_entry_auth_failed_on_invalid_auth(hass):
    client = _FakeClient(exc=InvalidAuth("bad password"))
    coordinator = AirportSoftwareCoordinator(hass, entry=None, client=client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_update_data_raises_update_failed_on_network_error(hass):
    client = _FakeClient(exc=ConnectionError("boom"))
    coordinator = AirportSoftwareCoordinator(hass, entry=None, client=client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


from custom_components.airport_software.coordinator import TowerDutyCoordinator
from custom_components.airport_software.models import TowerDutyStatus


class _FakeTowerDutyClient:
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    async def async_get_tower_duty(self, now):
        if self._exc is not None:
            raise self._exc
        return self._result


async def test_tower_duty_update_data_returns_client_result(hass):
    duty = TowerDutyStatus(on_duty="Rey, Elena", note=None)
    client = _FakeTowerDutyClient(result=duty)
    coordinator = TowerDutyCoordinator(hass, entry=None, client=client)

    assert await coordinator._async_update_data() == duty


async def test_tower_duty_update_data_raises_config_entry_auth_failed_on_invalid_auth(hass):
    client = _FakeTowerDutyClient(exc=InvalidAuth("bad password"))
    coordinator = TowerDutyCoordinator(hass, entry=None, client=client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_tower_duty_update_data_raises_update_failed_on_network_error(hass):
    client = _FakeTowerDutyClient(exc=ConnectionError("boom"))
    coordinator = TowerDutyCoordinator(hass, entry=None, client=client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
