"""Stateful HTTP client for an airport-software instance."""
from __future__ import annotations

import datetime as dt
from dataclasses import replace

import aiohttp

from .parsing import (
    extract_hidden_fields,
    login_failed,
    parse_flynow_table,
    parse_status_table,
    parse_tower_duty,
)
from .models import AircraftStatus, TowerDutyStatus

_LOGIN_PATH = "/login/login.aspx"
_OVERVIEW_PATH = "/internal/booking_overview.aspx"
_FLYNOW_PATH = "/internal/booking_flynow.aspx"
_KALENDER_PATH = "/internal/kalender.aspx"
_LOGIN_MARKER = 'id="ctl00_MainContentPlaceHolder_txtUserName"'
_FLUGLTG_SELECTED_MARKER = 'selected="selected" value="FLUGLTG"'

_POST_FIELD_ORDER = [
    "__EVENTTARGET",
    "__EVENTARGUMENT",
    "__VIEWSTATE",
    "__VIEWSTATEGENERATOR",
    "__EVENTVALIDATION",
    "ctl00$MainContentPlaceHolder$txtUserName",
    "ctl00$MainContentPlaceHolder$txtPassword",
    "ctl00$txtSequenz",
    "ctl00$txtGUID",
    "ctl00$TabOk",
]


class InvalidAuth(Exception):
    """Raised when the site rejects the configured credentials."""


class AirportSoftwareClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        username: str,
        password: str,
        enable_free_rest_of_day: bool = True,
        free_rest_of_day_cutoff: str = "18:00",
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._enable_free_rest_of_day = enable_free_rest_of_day
        self._free_rest_of_day_cutoff = free_rest_of_day_cutoff
        self._authenticated = False
        self._auth_failed = False

    async def async_get_status(self) -> list[AircraftStatus]:
        if self._auth_failed:
            raise InvalidAuth("airport-software previously rejected these credentials")

        if not self._authenticated:
            await self._async_login()

        overview_html = await self._async_fetch_with_relogin(_OVERVIEW_PATH)
        statuses = parse_status_table(overview_html)
        if not self._enable_free_rest_of_day:
            return statuses

        flynow_html = await self._async_fetch_with_relogin(_FLYNOW_PATH)
        flynow_data = parse_flynow_table(flynow_html, cutoff=self._free_rest_of_day_cutoff)
        return [
            replace(
                status,
                available_from_today=flynow_data.get(status.tail_number, (None, False))[0],
                free_rest_of_day=flynow_data.get(status.tail_number, (None, False))[1],
            )
            for status in statuses
        ]

    async def async_get_tower_duty(self, now: dt.datetime) -> TowerDutyStatus | None:
        if self._auth_failed:
            raise InvalidAuth("airport-software previously rejected these credentials")
        if not self._authenticated:
            await self._async_login()

        page_html = await self._async_fetch_with_relogin(_KALENDER_PATH)

        if _FLUGLTG_SELECTED_MARKER not in page_html:
            page_html = await self._async_select_flugleitung_calendar(page_html)

        return parse_tower_duty(page_html, now)

    async def _async_select_flugleitung_calendar(self, page_html: str) -> str:
        url = f"{self._base_url}{_KALENDER_PATH}"
        fields = extract_hidden_fields(page_html)
        fields["__EVENTTARGET"] = "ctl00$MainContentPlaceHolder$cmdPruefe"
        fields["__EVENTARGUMENT"] = ""
        fields["ctl00$MainContentPlaceHolder$lstKalender"] = "FLUGLTG"
        async with self._session.post(url, data=fields) as response:
            return await response.text()

    async def _async_fetch_with_relogin(self, path: str) -> str:
        """Fetch a page, re-authenticating once if the session has expired.

        Each page is checked (and re-fetched after a fresh login) on its
        own, immediately after it comes back — never fetched speculatively
        ahead of that check. Fetching pages as a pair and only checking
        afterward would, on an expired session, waste a fetch of the
        *second* page before discovering the *first* page bounced to the
        login screen, then fetch the second page again post-relogin.
        """
        page_html = await self._async_fetch(path)
        if self._looks_like_login_page(page_html):
            await self._async_login()
            page_html = await self._async_fetch(path)
        return page_html

    async def _async_fetch(self, path: str) -> str:
        url = f"{self._base_url}{path}"
        async with self._session.get(url) as response:
            return await response.text()

    @staticmethod
    def _looks_like_login_page(page_html: str) -> bool:
        return _LOGIN_MARKER in page_html

    async def _async_login(self) -> None:
        login_url = f"{self._base_url}{_LOGIN_PATH}"

        async with self._session.get(login_url) as response:
            page_html = await response.text()

        fields = extract_hidden_fields(page_html)
        fields["__EVENTTARGET"] = "ctl00$MainContentPlaceHolder$cmdLogin"
        fields["__EVENTARGUMENT"] = ""
        fields["ctl00$MainContentPlaceHolder$txtUserName"] = self._username
        fields["ctl00$MainContentPlaceHolder$txtPassword"] = self._password
        fields.pop("ctl00$MainContentPlaceHolder$cmdLogin", None)

        body = {key: fields[key] for key in _POST_FIELD_ORDER}

        headers = {
            "Referer": login_url,
            "Origin": self._base_url,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            ),
            "Cache-Control": "max-age=0",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

        async with self._session.post(login_url, data=body, headers=headers) as response:
            result_html = await response.text()

        if login_failed(result_html):
            self._authenticated = False
            self._auth_failed = True
            raise InvalidAuth("airport-software rejected the configured credentials")

        self._authenticated = True
