"""Pure-function HTML parsing for airport-software pages.

No network I/O lives here — client.py owns the HTTP layer and calls
into these functions with already-fetched response bodies.
"""
import html as html_module
import re

_HIDDEN_FIELD_RE = re.compile(r'<input[^>]*type="hidden"[^>]*>')
_NAME_RE = re.compile(r'name="([^"]+)"')
_VALUE_RE = re.compile(r'value="([^"]*)"')


def extract_hidden_fields(page_html: str) -> dict[str, str]:
    """Return {name: value} for every hidden <input> in an ASP.NET page."""
    fields: dict[str, str] = {}
    for match in _HIDDEN_FIELD_RE.finditer(page_html):
        tag = match.group(0)
        name_match = _NAME_RE.search(tag)
        if not name_match:
            continue
        value_match = _VALUE_RE.search(tag)
        fields[name_match.group(1)] = value_match.group(1) if value_match else ""
    return fields


_ERROR_DIV_RE = re.compile(r'<div id="ctl00_fehlertext" class="meldungen_err">')


def login_failed(response_html: str) -> bool:
    """True if a login POST response is the login page re-rendered with an error."""
    return bool(_ERROR_DIV_RE.search(response_html))


from .models import AircraftStatus, TowerDutyStatus

_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_ZUSTAND_TABLE_RE = re.compile(
    r'<div id="ctl00_MainContentPlaceHolder_divZustand">\s*<table[^>]*>(.*?)</table>\s*</div>',
    re.DOTALL,
)
_INFO_COUNT_RE = re.compile(r"\((\d+)\s+Infos\)")
_HOURS_RE = re.compile(r"(-?\d+):(\d+)")
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _strip_tags(fragment: str) -> str:
    """Strip HTML tags from a fragment that has no embedded fake tags.

    Only safe to use on cells that don't contain tooltip onmouseover
    attributes with literal <p> tags inside them (see the remaining-hours
    cell, which uses _parse_remaining_hours instead for exactly this
    reason).
    """
    fragment = _BR_RE.sub("\n", fragment)
    fragment = _TAG_RE.sub("", fragment)
    return html_module.unescape(fragment).strip()


def _parse_remaining_hours(cell: str) -> float:
    """Extract HH:MM from the remaining-hours cell.

    Deliberately does NOT strip tags first: this cell's <a> tag carries an
    onmouseover="...showTip('<p>...</p>')..." attribute containing literal,
    unescaped <p> tags inside a JS string. A generic tag-stripper would stop
    at the first '>' inside that attribute and mangle the result. Searching
    directly for the digit:digit pattern sidesteps the problem entirely.
    """
    match = _HOURS_RE.search(cell)
    if not match:
        raise ValueError(f"could not parse remaining hours from cell: {cell!r}")
    sign_str, minutes_str = match.groups()
    negative = sign_str.startswith("-")
    hours = int(sign_str.lstrip("-"))
    total = hours + int(minutes_str) / 60
    return -total if negative else total


def _parse_row(row_html: str) -> AircraftStatus:
    cells = _CELL_RE.findall(row_html)
    if len(cells) != 5:
        raise ValueError(f"expected 5 cells in status row, got {len(cells)}: {row_html!r}")

    tail_number = _strip_tags(cells[0])
    in_use = "key_out.png" in cells[1]

    condition_text = _strip_tags(cells[2])
    if condition_text.startswith("Wartung"):
        condition = "maintenance"
        open_info_count = 0
    else:
        condition = "ready"
        info_match = _INFO_COUNT_RE.search(condition_text)
        open_info_count = int(info_match.group(1)) if info_match else 0

    remaining_hours = _parse_remaining_hours(cells[3])
    remarks = _strip_tags(cells[4])

    return AircraftStatus(
        tail_number=tail_number,
        in_use=in_use,
        condition=condition,
        open_info_count=open_info_count,
        remaining_hours=remaining_hours,
        remarks=remarks,
    )


def parse_status_table(page_html: str) -> list[AircraftStatus]:
    """Parse the aircraft status table into a list of AircraftStatus."""
    table_match = _ZUSTAND_TABLE_RE.search(page_html)
    if not table_match:
        raise ValueError("status table not found in page")
    rows = _ROW_RE.findall(table_match.group(1))
    data_rows = [row for row in rows if "<th" not in row]
    return [_parse_row(row) for row in data_rows]


_FLYNOW_TABLE_RE = re.compile(
    r'<div id="ctl00_MainContentPlaceHolder_divBookingList">\s*<table[^>]*>(.*?)</table>\s*</div>',
    re.DOTALL,
)
_IMMEDIATE_MARKER = "Sofort"
_END_OF_DAY_MARKER = "Ende des Tages"


def _time_to_minutes(value: str) -> int:
    hours_str, minutes_str = value.split(":")
    return int(hours_str) * 60 + int(minutes_str)


def parse_flynow_table(
    page_html: str, cutoff: str = "18:00"
) -> dict[str, tuple[str, bool]]:
    """Parse booking_flynow.aspx into {tail_number: (available_from_today, free_rest_of_day)}.

    Aircraft with no open slot for the rest of the day are simply absent
    from the source table, and therefore absent from this result — callers
    must treat a missing tail number as (None, False).

    free_rest_of_day is True only when the aircraft has no later booking
    today ("Verfuegbar bis" == "Ende des Tages") AND its available-from
    time is at or before `cutoff` ("Sofort" always counts as before cutoff).
    """
    cutoff_minutes = _time_to_minutes(cutoff)

    table_match = _FLYNOW_TABLE_RE.search(page_html)
    if not table_match:
        raise ValueError("flynow table not found in page")
    rows = _ROW_RE.findall(table_match.group(1))
    data_rows = [row for row in rows if "<th" not in row]

    result: dict[str, tuple[str, bool]] = {}
    for row in data_rows:
        cells = _CELL_RE.findall(row)
        if len(cells) != 4:
            raise ValueError(f"expected 4 cells in flynow row, got {len(cells)}: {row!r}")

        tail_number = _strip_tags(cells[0])
        available_from_text = _strip_tags(cells[1])
        available_until_text = _strip_tags(cells[2])

        free_until_end_of_day = available_until_text == _END_OF_DAY_MARKER
        if available_from_text == _IMMEDIATE_MARKER:
            available_from_today = "immediate"
            within_cutoff = True
        else:
            available_from_today = available_from_text
            within_cutoff = _time_to_minutes(available_from_text) <= cutoff_minutes

        result[tail_number] = (available_from_today, free_until_end_of_day and within_cutoff)

    return result


import datetime as dt

_GERMAN_MONTHS = {
    "Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6,
    "Juli": 7, "August": 8, "September": 9, "Oktober": 10, "November": 11, "Dezember": 12,
}
_KALENDER_HEADER_RE = re.compile(r"Kalender: Flugleitung (\w+) (\d{4})")
_KALENDER_TABLE_RE = re.compile(
    r'<div id="ctl00_MainContentPlaceHolder_divKalenderList">\s*<table[^>]*>(.*?)</table>\s*</div>',
    re.DOTALL,
)
_DAY_HEADER_RE = re.compile(r"<th[^>]*>[^,<]*,\s*(\d{1,2})</th>")
_TIME_RANGE_RE = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")
_TOOLTIP_NOTE_RE = re.compile(r"boxcontent\\'>([^<]*)<")


def _clean_duty_name(cell: str) -> str:
    """Extract the plain name text preceding any tooltip <a> link.

    Cells can look like "Beispiel, Max  <a ...tooltip markup...>" where the
    tooltip's onmouseover attribute contains literal, unescaped <p> tags —
    the same quirk as the remaining-hours cell in the overview table — so
    this takes everything before the <a rather than stripping all tags.
    """
    before_link = re.split(r"<a\s", cell)[0]
    return html_module.unescape(before_link).strip()


def _extract_duty_note(cell: str) -> str | None:
    match = _TOOLTIP_NOTE_RE.search(cell)
    return html_module.unescape(match.group(1)).strip() if match else None


def parse_tower_duty(page_html: str, now: dt.datetime) -> TowerDutyStatus | None:
    """Who is on Flugleitung (tower) duty at `now`."""
    header_match = _KALENDER_HEADER_RE.search(page_html)
    if not header_match:
        return None
    month = _GERMAN_MONTHS.get(header_match.group(1))
    year = int(header_match.group(2))
    if month is None:
        return None

    table_match = _KALENDER_TABLE_RE.search(page_html)
    if not table_match:
        return None

    for row in _ROW_RE.findall(table_match.group(1)):
        day_match = _DAY_HEADER_RE.search(row)
        if not day_match:
            continue
        try:
            row_date = dt.date(year, month, int(day_match.group(1)))
        except ValueError:
            continue
        if row_date != now.date():
            continue

        cells = _CELL_RE.findall(row)
        for i in range(0, len(cells) - 1, 2):
            time_match = _TIME_RANGE_RE.search(cells[i])
            if not time_match:
                continue
            start_h, start_m, end_h, end_m = (int(g) for g in time_match.groups())
            start = dt.time(start_h, start_m)
            current = now.time()
            in_window = (
                current >= start
                if end_h == 24
                else start <= current <= dt.time(end_h, end_m)
            )
            if in_window:
                name_cell = cells[i + 1]
                return TowerDutyStatus(
                    on_duty=_clean_duty_name(name_cell),
                    note=_extract_duty_note(name_cell),
                )
        return TowerDutyStatus(on_duty=None, note=None)

    return None
