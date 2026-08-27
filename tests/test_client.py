import datetime as dt

import aiohttp
import pytest
from aioresponses import aioresponses

from tests.conftest import load_fixture
from custom_components.airport_software.client import AirportSoftwareClient, InvalidAuth
from custom_components.airport_software.models import TowerDutyStatus

BASE_URL = "https://example.test"
LOGIN_URL = f"{BASE_URL}/login/login.aspx"
OVERVIEW_URL = f"{BASE_URL}/internal/booking_overview.aspx"
FLYNOW_URL = f"{BASE_URL}/internal/booking_flynow.aspx"
KALENDER_URL = f"{BASE_URL}/internal/kalender.aspx"


async def test_async_get_status_merges_overview_and_flynow_by_default():
    login_page = load_fixture("login_page.html")
    login_success = load_fixture("login_response_success.html")
    overview_page = load_fixture("booking_overview.html")
    flynow_page = load_fixture("booking_flynow.html")

    with aioresponses() as mocked:
        mocked.get(LOGIN_URL, body=login_page)
        mocked.post(LOGIN_URL, body=login_success)
        mocked.get(OVERVIEW_URL, body=overview_page)
        mocked.get(FLYNOW_URL, body=flynow_page)

        async with aiohttp.ClientSession() as session:
            client = AirportSoftwareClient(session, BASE_URL, "1234", "secret")
            statuses = await client.async_get_status()

    by_tail = {s.tail_number: s for s in statuses}
    assert len(statuses) == 4
    assert by_tail["D-ABCD"].available_from_today == "immediate"
    assert by_tail["D-ABCD"].free_rest_of_day is True
    assert by_tail["D-IJKL"].free_rest_of_day is False  # available only from 20:00
    # D-MNOP is absent from the flynow fixture entirely -> defaults apply
    assert by_tail["D-MNOP"].available_from_today is None
    assert by_tail["D-MNOP"].free_rest_of_day is False


async def test_async_get_status_respects_custom_cutoff():
    login_page = load_fixture("login_page.html")
    login_success = load_fixture("login_response_success.html")
    overview_page = load_fixture("booking_overview.html")
    flynow_page = load_fixture("booking_flynow.html")

    with aioresponses() as mocked:
        mocked.get(LOGIN_URL, body=login_page)
        mocked.post(LOGIN_URL, body=login_success)
        mocked.get(OVERVIEW_URL, body=overview_page)
        mocked.get(FLYNOW_URL, body=flynow_page)

        async with aiohttp.ClientSession() as session:
            client = AirportSoftwareClient(
                session, BASE_URL, "1234", "secret", free_rest_of_day_cutoff="20:30"
            )
            statuses = await client.async_get_status()

    by_tail = {s.tail_number: s for s in statuses}
    assert by_tail["D-IJKL"].free_rest_of_day is True  # 20:00 <= 20:30 cutoff now


async def test_async_get_status_skips_flynow_when_disabled():
    login_page = load_fixture("login_page.html")
    login_success = load_fixture("login_response_success.html")
    overview_page = load_fixture("booking_overview.html")

    with aioresponses() as mocked:
        mocked.get(LOGIN_URL, body=login_page)
        mocked.post(LOGIN_URL, body=login_success)
        mocked.get(OVERVIEW_URL, body=overview_page)
        # No FLYNOW_URL mock registered: if the client tried to fetch it,
        # aioresponses would raise ClientConnectionError, failing this test.

        async with aiohttp.ClientSession() as session:
            client = AirportSoftwareClient(
                session, BASE_URL, "1234", "secret", enable_free_rest_of_day=False
            )
            statuses = await client.async_get_status()

    by_tail = {s.tail_number: s for s in statuses}
    assert by_tail["D-ABCD"].available_from_today is None
    assert by_tail["D-ABCD"].free_rest_of_day is False


async def test_async_get_status_raises_invalid_auth_on_rejected_credentials():
    login_page = load_fixture("login_page.html")
    login_invalid = load_fixture("login_response_invalid.html")

    with aioresponses() as mocked:
        mocked.get(LOGIN_URL, body=login_page)
        mocked.post(LOGIN_URL, body=login_invalid)

        async with aiohttp.ClientSession() as session:
            client = AirportSoftwareClient(session, BASE_URL, "1234", "wrong")
            with pytest.raises(InvalidAuth):
                await client.async_get_status()


async def test_async_get_status_does_not_retry_login_after_invalid_auth():
    """A second call must not silently re-attempt login with the same bad password."""
    login_page = load_fixture("login_page.html")
    login_invalid = load_fixture("login_response_invalid.html")

    with aioresponses() as mocked:
        mocked.get(LOGIN_URL, body=login_page)
        mocked.post(LOGIN_URL, body=login_invalid)

        async with aiohttp.ClientSession() as session:
            client = AirportSoftwareClient(session, BASE_URL, "1234", "wrong")
            with pytest.raises(InvalidAuth):
                await client.async_get_status()
            # No more mocked responses registered: a second network attempt
            # here would raise aioresponses.ClientConnectionError, not
            # InvalidAuth — proving the caller (coordinator) is the one
            # responsible for not calling again, not the client retrying.
            with pytest.raises(InvalidAuth):
                await client.async_get_status()


async def test_async_get_status_relogs_in_when_session_expires():
    """If a fetch bounces back to the login page, log in again once and retry."""
    login_page = load_fixture("login_page.html")
    login_success = load_fixture("login_response_success.html")
    overview_page = load_fixture("booking_overview.html")
    flynow_page = load_fixture("booking_flynow.html")

    with aioresponses() as mocked:
        mocked.get(LOGIN_URL, body=login_page)
        mocked.post(LOGIN_URL, body=login_success)
        mocked.get(OVERVIEW_URL, body=login_page)  # session already "expired"
        mocked.get(LOGIN_URL, body=login_page)
        mocked.post(LOGIN_URL, body=login_success)
        mocked.get(OVERVIEW_URL, body=overview_page)
        mocked.get(FLYNOW_URL, body=flynow_page)

        async with aiohttp.ClientSession() as session:
            client = AirportSoftwareClient(session, BASE_URL, "1234", "secret")
            statuses = await client.async_get_status()

    assert len(statuses) == 4


async def test_async_get_tower_duty_switches_calendar_type_if_needed():
    login_page = load_fixture("login_page.html")
    login_success = load_fixture("login_response_success.html")
    wrong_type_page = load_fixture("kalender_wrong_type.html")
    correct_page = load_fixture("kalender.html")

    with aioresponses() as mocked:
        mocked.get(LOGIN_URL, body=login_page)
        mocked.post(LOGIN_URL, body=login_success)
        mocked.get(KALENDER_URL, body=wrong_type_page)
        mocked.post(KALENDER_URL, body=correct_page)

        async with aiohttp.ClientSession() as session:
            client = AirportSoftwareClient(session, BASE_URL, "1234", "secret")
            result = await client.async_get_tower_duty(dt.datetime(2026, 1, 14, 10, 0))

    assert result == TowerDutyStatus(on_duty="Mustermann, Erika", note=None)


async def test_async_get_tower_duty_skips_switch_when_already_selected():
    login_page = load_fixture("login_page.html")
    login_success = load_fixture("login_response_success.html")
    correct_page = load_fixture("kalender.html")

    with aioresponses() as mocked:
        mocked.get(LOGIN_URL, body=login_page)
        mocked.post(LOGIN_URL, body=login_success)
        mocked.get(KALENDER_URL, body=correct_page)
        # No POST to KALENDER_URL registered: if the client tried to switch
        # calendar type anyway, aioresponses would raise, failing this test.

        async with aiohttp.ClientSession() as session:
            client = AirportSoftwareClient(session, BASE_URL, "1234", "secret")
            result = await client.async_get_tower_duty(dt.datetime(2026, 1, 14, 10, 0))

    assert result == TowerDutyStatus(on_duty="Mustermann, Erika", note=None)
