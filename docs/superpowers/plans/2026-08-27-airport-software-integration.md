# airport-software Home Assistant Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a HACS-installable Home Assistant custom integration that logs into an airport-software reservation system instance and reports each aircraft's status (in-use, condition, remaining hours, remarks) as entities, polled every 15 minutes.

**Architecture:** A `custom_components/airport_software/` package: pure-function HTML parsing (`parsing.py`), a stateful `aiohttp`-based client that replicates the validated ASP.NET WebForms login postback (`client.py`), a `DataUpdateCoordinator` (`coordinator.py`) that turns client errors into either a hard auth-failure stop or a soft retry, a `ConfigFlow` for setup/reauth, and `binary_sensor`/`sensor` platforms.

**Tech Stack:** Python 3.13, Home Assistant custom integration APIs (`homeassistant.helpers.update_coordinator`, `homeassistant.config_entries`), `aiohttp` for HTTP, `pytest` + `pytest-asyncio` + `aioresponses` for client/parsing tests, `pytest-homeassistant-custom-component` for coordinator/config-flow/entity tests.

**Spec:** `docs/superpowers/specs/2026-08-27-airport-software-integration-design.md`

## Global Constraints

- No automated test ever performs a live login against a real airport-software instance — all HTTP is mocked (`aioresponses`) or fixture-driven, per the spec's lockout-risk finding.
- On the client detecting rejected credentials, raise `InvalidAuth` — the coordinator must convert this to `ConfigEntryAuthFailed`, which stops automatic polling entirely (no retry loop against the real site).
- Login POST must set `__EVENTTARGET=ctl00$MainContentPlaceHolder$cmdLogin` and `__EVENTARGUMENT=""`, and must NOT include a `ctl00$MainContentPlaceHolder$cmdLogin` field (validated finding from the spec's Background section).
- Base URL, member number, and password are all user-configurable via the config flow (generic, HACS-shareable — not hardcoded to any one club).
- Follow immutability style: `AircraftStatus` is a frozen dataclass; no in-place mutation of it.

---

## Task 1: Project scaffolding

**Files:**
- Create: `custom_components/airport_software/manifest.json`
- Create: `custom_components/airport_software/const.py`
- Create: `custom_components/airport_software/strings.json`
- Create: `custom_components/airport_software/translations/en.json`
- Create: `hacs.json`
- Create: `requirements_test.txt`
- Create: `pytest.ini`
- Create: `tests/conftest.py`
- Create: `.gitignore` additions (already has `.env`, `__pycache__/`, `.venv/` from design phase)

**Interfaces:**
- Produces: `DOMAIN = "airport_software"`, `POLL_INTERVAL_SECONDS = 900`, `CONF_BASE_URL = "base_url"`, `CONF_USERNAME = "username"`, `CONF_PASSWORD = "password"` — every later task imports these from `const.py`.

- [ ] **Step 1: Create the integration manifest**

```json
{
  "domain": "airport_software",
  "name": "airport-software",
  "codeowners": ["@jgilla"],
  "config_flow": true,
  "documentation": "https://github.com/jgilla/ha-airport-software",
  "integration_type": "hub",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/jgilla/ha-airport-software/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

- [ ] **Step 2: Create `const.py`**

```python
"""Constants for the airport-software integration."""

DOMAIN = "airport_software"
POLL_INTERVAL_SECONDS = 900

CONF_BASE_URL = "base_url"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
```

- [ ] **Step 3: Create `strings.json` and `translations/en.json`** (identical content — HA requires both)

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Connect to airport-software",
        "data": {
          "base_url": "Base URL (e.g. https://fly-mainz.de)",
          "username": "Member number",
          "password": "Password"
        }
      },
      "reauth_confirm": {
        "title": "Re-authenticate with airport-software",
        "data": {
          "password": "Password"
        }
      }
    },
    "error": {
      "invalid_auth": "Invalid member number or password.",
      "cannot_connect": "Could not reach the site. Check the base URL."
    },
    "abort": {
      "reauth_successful": "Re-authentication was successful."
    }
  }
}
```

Copy this exact content into both `custom_components/airport_software/strings.json` and `custom_components/airport_software/translations/en.json`.

- [ ] **Step 4: Create `hacs.json` at the repo root**

```json
{
  "name": "airport-software",
  "content_in_root": false,
  "render_readme": true
}
```

- [ ] **Step 5: Create `requirements_test.txt` at the repo root**

```
pytest==8.3.3
pytest-asyncio==0.24.0
aioresponses==0.7.6
pytest-homeassistant-custom-component==0.13.196
```

- [ ] **Step 6: Create `pytest.ini` at the repo root**

```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 7: Create `tests/conftest.py`**

```python
"""Shared test fixtures."""
from pathlib import Path

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components importable in every test."""
    yield
```

- [ ] **Step 8: Install test dependencies and verify pytest collects (no tests yet)**

Run: `pip install -r requirements_test.txt && pytest --collect-only`
Expected: exits 0, "no tests ran" (or similar) — no import errors.

- [ ] **Step 9: Commit**

```bash
git add custom_components/airport_software/manifest.json custom_components/airport_software/const.py \
  custom_components/airport_software/strings.json custom_components/airport_software/translations/en.json \
  hacs.json requirements_test.txt pytest.ini tests/conftest.py
git commit -m "chore: scaffold airport_software integration package and test harness"
```

---

## Task 2: Data model

**Files:**
- Create: `custom_components/airport_software/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `AircraftStatus` frozen dataclass with fields `tail_number: str`, `in_use: bool`, `condition: Literal["ready", "maintenance"]`, `open_info_count: int`, `remaining_hours: float`, `remarks: str`. Every later task (`parsing.py`, `client.py`, `coordinator.py`, `sensor.py`, `binary_sensor.py`) imports this exact type.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from custom_components.airport_software.models import AircraftStatus


def test_aircraft_status_is_frozen():
    status = AircraftStatus(
        tail_number="D-ABCD",
        in_use=False,
        condition="ready",
        open_info_count=0,
        remaining_hours=82.083,
        remarks="All good.",
    )
    assert status.tail_number == "D-ABCD"
    try:
        status.tail_number = "D-WXYZ"
        assert False, "expected FrozenInstanceError"
    except AttributeError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.airport_software.models'`

- [ ] **Step 3: Write the implementation**

```python
# custom_components/airport_software/models.py
"""Data model for a single aircraft's status."""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AircraftStatus:
    tail_number: str
    in_use: bool
    condition: Literal["ready", "maintenance"]
    open_info_count: int
    remaining_hours: float
    remarks: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/models.py tests/test_models.py
git commit -m "feat: add AircraftStatus data model"
```

---

## Task 3: Login field extraction

**Files:**
- Create: `custom_components/airport_software/parsing.py`
- Create: `tests/fixtures/login_page.html`
- Test: `tests/test_parsing_login.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `extract_hidden_fields(html: str) -> dict[str, str]` — Task 5 (`client.py`) calls this on the login page GET response.

- [ ] **Step 1: Create the fixture**

```html
<!-- tests/fixtures/login_page.html -->
<html><body>
<form name="aspnetForm" method="post" action="./login.aspx" id="aspnetForm">
<input type="hidden" name="__EVENTTARGET" id="__EVENTTARGET" value="" />
<input type="hidden" name="__EVENTARGUMENT" id="__EVENTARGUMENT" value="" />
<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="FAKEVIEWSTATE123==" />
<input type="hidden" name="__VIEWSTATEGENERATOR" id="__VIEWSTATEGENERATOR" value="CA0B0334" />
<input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="FAKEEVENTVALIDATION==" />
<input name="ctl00$MainContentPlaceHolder$txtUserName" type="text" id="ctl00_MainContentPlaceHolder_txtUserName" />
<input name="ctl00$MainContentPlaceHolder$txtPassword" type="password" id="ctl00_MainContentPlaceHolder_txtPassword" />
<input type="submit" name="ctl00$MainContentPlaceHolder$cmdLogin" value="LogIn" id="ctl00_MainContentPlaceHolder_cmdLogin" />
<input name="ctl00$txtSequenz" type="hidden" id="ctl00_txtSequenz" value="1" />
<input name="ctl00$txtGUID" type="hidden" id="ctl00_txtGUID" value="00000000-0000-0000-0000-000000000000" />
<input name="ctl00$TabOk" type="hidden" id="ctl00_TabOk" />
</form>
</body></html>
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_parsing_login.py
from tests.conftest import load_fixture
from custom_components.airport_software.parsing import extract_hidden_fields


def test_extract_hidden_fields_reads_all_hidden_inputs():
    html = load_fixture("login_page.html")
    fields = extract_hidden_fields(html)
    assert fields["__VIEWSTATE"] == "FAKEVIEWSTATE123=="
    assert fields["__VIEWSTATEGENERATOR"] == "CA0B0334"
    assert fields["__EVENTVALIDATION"] == "FAKEEVENTVALIDATION=="
    assert fields["ctl00$txtSequenz"] == "1"
    assert fields["ctl00$txtGUID"] == "00000000-0000-0000-0000-000000000000"
    assert fields["ctl00$TabOk"] == ""


def test_extract_hidden_fields_excludes_visible_inputs():
    html = load_fixture("login_page.html")
    fields = extract_hidden_fields(html)
    assert "ctl00$MainContentPlaceHolder$txtUserName" not in fields
    assert "ctl00$MainContentPlaceHolder$cmdLogin" not in fields
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_parsing_login.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.airport_software.parsing'`

- [ ] **Step 4: Write the implementation**

```python
# custom_components/airport_software/parsing.py
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_parsing_login.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add custom_components/airport_software/parsing.py tests/fixtures/login_page.html tests/test_parsing_login.py
git commit -m "feat: add ASP.NET hidden-field extraction"
```

---

## Task 4: Login failure detection

**Files:**
- Modify: `custom_components/airport_software/parsing.py`
- Create: `tests/fixtures/login_response_invalid.html`
- Create: `tests/fixtures/login_response_success.html`
- Test: `tests/test_parsing_login.py` (append)

**Interfaces:**
- Consumes: `parsing.py` from Task 3 (same file, appended to).
- Produces: `login_failed(response_html: str) -> bool` — Task 5 (`client.py`) calls this on the login POST response to decide whether to raise `InvalidAuth`.

- [ ] **Step 1: Create the fixtures**

```html
<!-- tests/fixtures/login_response_invalid.html -->
<html><body>
<form name="aspnetForm" method="post" action="./login.aspx" id="aspnetForm">
<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="FAKEVIEWSTATE456==" />
<div id="ctl00_fehlertext" class="meldungen_err"><ul><li>Das Passwort f&uuml;r den Benutzer TESTUSER ist ung&uuml;ltig! Noch 14 Versuche verbleiben.</li></ul></div>
<input name="ctl00$MainContentPlaceHolder$txtUserName" type="text" id="ctl00_MainContentPlaceHolder_txtUserName" value="1234" />
<input name="ctl00$MainContentPlaceHolder$txtPassword" type="password" id="ctl00_MainContentPlaceHolder_txtPassword" />
</form>
</body></html>
```

```html
<!-- tests/fixtures/login_response_success.html -->
<html><body>
<div class="logout"><a id="ctl00_cmdLogout" href="javascript:__doPostBack('ctl00$cmdLogout','')">Angemeldet als TESTUSER (1234). Abmelden!</a></div>
<div id="ctl00_MainContentPlaceHolder_divZustand"><table></table></div>
</body></html>
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_parsing_login.py (append)
from custom_components.airport_software.parsing import login_failed


def test_login_failed_true_on_error_page():
    html = load_fixture("login_response_invalid.html")
    assert login_failed(html) is True


def test_login_failed_false_on_success_page():
    html = load_fixture("login_response_success.html")
    assert login_failed(html) is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_parsing_login.py -v`
Expected: FAIL with `ImportError: cannot import name 'login_failed'`

- [ ] **Step 4: Write the implementation**

```python
# custom_components/airport_software/parsing.py (append)
_ERROR_DIV_RE = re.compile(r'<div id="ctl00_fehlertext" class="meldungen_err">')


def login_failed(response_html: str) -> bool:
    """True if a login POST response is the login page re-rendered with an error."""
    return bool(_ERROR_DIV_RE.search(response_html))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_parsing_login.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add custom_components/airport_software/parsing.py tests/fixtures/login_response_invalid.html \
  tests/fixtures/login_response_success.html tests/test_parsing_login.py
git commit -m "feat: detect rejected-credentials login response"
```

---

## Task 5: Status table parsing

**Files:**
- Modify: `custom_components/airport_software/parsing.py`
- Create: `tests/fixtures/booking_overview.html`
- Test: `tests/test_parsing_overview.py`

**Interfaces:**
- Consumes: `AircraftStatus` (Task 2).
- Produces: `parse_status_table(page_html: str) -> list[AircraftStatus]` — Task 6 (`client.py`) calls this on the overview page GET response.

- [ ] **Step 1: Create the fixture**

This reproduces the real page's structure, including the tooltip `onmouseover` attribute containing literal (unescaped) `<p>` tags inside a JS string — a real quirk from the live site that breaks naive "strip all `<...>`" parsing, so the parser must extract the remaining-hours value with a targeted digit pattern instead of generic tag-stripping.

```html
<!-- tests/fixtures/booking_overview.html -->
<html><body>
<form name="aspnetForm" method="post" action="./booking_overview.aspx" id="aspnetForm">
<div id="ctl00_MainContentPlaceHolder_divZustand"><table width="100%"><colgroup><col width="70"><col width="15"><col width="105"><col width="70"></colgroup><tr><th colspan="2" style="text-align:center;">Rufzeichen</th><th>Zustand</th><th>RestStd.</th><th>Bemerkung</th></tr><tr><td>D-ABCD</td><td><img src="../style/design/key.png" alt="Schl&uuml;ssel verf&uuml;gbar" /></td><td>Klar</td><td class="grid_rightalign"><a class="stdlink_tooltip" onmouseover="return(showTip('<p class=\'boxhead\'>Stundenstatus D-ABCD</p><p class=\'boxcontent\'>Flugstundenberechnung basierend auf letztem Chartereintrag</p>'));" onmouseout="hideTip();">82:05</a></td><td><b></b>All good.</td></tr><tr><td>D-EFGH</td><td><img src="../style/design/key_out.png" alt="Schl&uuml;ssel ausgegeben" /></td><td><a href="mangel.aspx?link=1" target="_blank" onclick="return(pop_window('mangel.aspx?link=1','Buchungssystem'));">Klar (3 Infos)</a></td><td class="grid_rightalign overviewgrid_red"><a class="stdlink_tooltip" onmouseover="return(showTip('<p>x</p>'));" onmouseout="hideTip();">-11:25</a></td><td><b></b>Minor issue.<br /><br />Second line.</td></tr><tr><td>D-IJKL</td><td><img src="../style/design/key.png" alt="Schl&uuml;ssel verf&uuml;gbar" /></td><td class="overviewgrid_red"><a href="mangel.aspx?link=2" target="_blank" onclick="return(pop_window('mangel.aspx?link=2','Buchungssystem'));">Wartung</a></td><td class="grid_rightalign"><a class="stdlink_tooltip" onmouseover="return(showTip('x'));" onmouseout="hideTip();">43:38</a></td><td><b></b>In for maintenance.</td></tr><tr><td>D-MNOP</td><td><img src="../style/design/key.png" alt="Schl&uuml;ssel verf&uuml;gbar" /></td><td class="overviewgrid_red">Wartung</td><td class="grid_rightalign"><a class="stdlink_tooltip" onmouseover="return(showTip('x'));" onmouseout="hideTip();">55:08</a></td><td><b></b>Engine work.</td></tr></table></div>
</form>
</body></html>
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_parsing_overview.py
from tests.conftest import load_fixture
from custom_components.airport_software.parsing import parse_status_table


def test_parse_status_table_returns_one_entry_per_aircraft():
    html = load_fixture("booking_overview.html")
    statuses = parse_status_table(html)
    assert [s.tail_number for s in statuses] == ["D-ABCD", "D-EFGH", "D-IJKL", "D-MNOP"]


def test_parse_status_table_available_ready_no_infos():
    html = load_fixture("booking_overview.html")
    statuses = {s.tail_number: s for s in parse_status_table(html)}
    d_abcd = statuses["D-ABCD"]
    assert d_abcd.in_use is False
    assert d_abcd.condition == "ready"
    assert d_abcd.open_info_count == 0
    assert d_abcd.remaining_hours == pytest.approx(82 + 5 / 60)
    assert d_abcd.remarks == "All good."


def test_parse_status_table_in_use_with_infos_and_negative_hours():
    html = load_fixture("booking_overview.html")
    statuses = {s.tail_number: s for s in parse_status_table(html)}
    d_efgh = statuses["D-EFGH"]
    assert d_efgh.in_use is True
    assert d_efgh.condition == "ready"
    assert d_efgh.open_info_count == 3
    assert d_efgh.remaining_hours == pytest.approx(-(11 + 25 / 60))
    assert d_efgh.remarks == "Minor issue.\n\nSecond line."


def test_parse_status_table_maintenance_with_link():
    html = load_fixture("booking_overview.html")
    statuses = {s.tail_number: s for s in parse_status_table(html)}
    d_ijkl = statuses["D-IJKL"]
    assert d_ijkl.condition == "maintenance"
    assert d_ijkl.open_info_count == 0


def test_parse_status_table_maintenance_plain_text():
    html = load_fixture("booking_overview.html")
    statuses = {s.tail_number: s for s in parse_status_table(html)}
    d_mnop = statuses["D-MNOP"]
    assert d_mnop.condition == "maintenance"
```

Add `import pytest` at the top of `tests/test_parsing_overview.py` (needed for `pytest.approx`).

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_parsing_overview.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_status_table'`

- [ ] **Step 4: Write the implementation**

```python
# custom_components/airport_software/parsing.py (append)
from .models import AircraftStatus

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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_parsing_overview.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add custom_components/airport_software/parsing.py tests/fixtures/booking_overview.html tests/test_parsing_overview.py
git commit -m "feat: parse aircraft status table into AircraftStatus list"
```

---

## Task 6: HTTP client

**Files:**
- Create: `custom_components/airport_software/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `extract_hidden_fields`, `login_failed`, `parse_status_table` (Tasks 3–5); `AircraftStatus` (Task 2).
- Produces: `AirportSoftwareClient(session: aiohttp.ClientSession, base_url: str, username: str, password: str)` with `async def async_get_status(self) -> list[AircraftStatus]`, and `InvalidAuth` exception — Task 7 (`coordinator.py`) constructs and calls this.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_client.py
import aiohttp
import pytest
from aioresponses import aioresponses

from tests.conftest import load_fixture
from custom_components.airport_software.client import AirportSoftwareClient, InvalidAuth

BASE_URL = "https://example.test"
LOGIN_URL = f"{BASE_URL}/login/login.aspx"
OVERVIEW_URL = f"{BASE_URL}/internal/booking_overview.aspx"


async def test_async_get_status_logs_in_then_returns_parsed_statuses():
    login_page = load_fixture("login_page.html")
    login_success = load_fixture("login_response_success.html")
    overview_page = load_fixture("booking_overview.html")

    with aioresponses() as mocked:
        mocked.get(LOGIN_URL, body=login_page)
        mocked.post(LOGIN_URL, body=login_success)
        mocked.get(OVERVIEW_URL, body=overview_page)

        async with aiohttp.ClientSession() as session:
            client = AirportSoftwareClient(session, BASE_URL, "1234", "secret")
            statuses = await client.async_get_status()

    assert len(statuses) == 4
    assert statuses[0].tail_number == "D-ABCD"


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
    """If the overview fetch bounces back to the login page, log in again once."""
    login_page = load_fixture("login_page.html")
    login_success = load_fixture("login_response_success.html")
    overview_page = load_fixture("booking_overview.html")

    with aioresponses() as mocked:
        mocked.get(LOGIN_URL, body=login_page)
        mocked.post(LOGIN_URL, body=login_success)
        mocked.get(OVERVIEW_URL, body=login_page)  # session already "expired"
        mocked.get(LOGIN_URL, body=login_page)
        mocked.post(LOGIN_URL, body=login_success)
        mocked.get(OVERVIEW_URL, body=overview_page)

        async with aiohttp.ClientSession() as session:
            client = AirportSoftwareClient(session, BASE_URL, "1234", "secret")
            statuses = await client.async_get_status()

    assert len(statuses) == 4
```

Note: `test_async_get_status_does_not_retry_login_after_invalid_auth` asserts the client raises `InvalidAuth` again on retry rather than attempting network I/O — this requires the client to remember it's in a failed-auth state and not attempt to re-login. Implement that behavior below.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.airport_software.client'`

- [ ] **Step 3: Write the implementation**

```python
# custom_components/airport_software/client.py
"""Stateful HTTP client for an airport-software instance."""
from __future__ import annotations

import aiohttp

from .parsing import extract_hidden_fields, login_failed, parse_status_table
from .models import AircraftStatus

_LOGIN_PATH = "/login/login.aspx"
_OVERVIEW_PATH = "/internal/booking_overview.aspx"
_LOGIN_MARKER = 'id="ctl00_MainContentPlaceHolder_txtUserName"'

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
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._authenticated = False
        self._auth_failed = False

    async def async_get_status(self) -> list[AircraftStatus]:
        if self._auth_failed:
            raise InvalidAuth("airport-software previously rejected these credentials")

        if not self._authenticated:
            await self._async_login()

        page_html = await self._async_fetch_overview()
        if self._looks_like_login_page(page_html):
            await self._async_login()
            page_html = await self._async_fetch_overview()

        return parse_status_table(page_html)

    async def _async_fetch_overview(self) -> str:
        url = f"{self._base_url}{_OVERVIEW_PATH}"
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_client.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/client.py tests/test_client.py
git commit -m "feat: add AirportSoftwareClient with validated login postback"
```

---

## Task 7: Coordinator

**Files:**
- Create: `custom_components/airport_software/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `AirportSoftwareClient`, `InvalidAuth` (Task 6); `AircraftStatus` (Task 2); `DOMAIN`, `POLL_INTERVAL_SECONDS` (Task 1).
- Produces: `AirportSoftwareCoordinator(hass, entry, client)` subclassing `DataUpdateCoordinator[dict[str, AircraftStatus]]` — Task 9 (`__init__.py`) constructs this; Tasks 10–11 (`binary_sensor.py`, `sensor.py`) read `coordinator.data`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_coordinator.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_coordinator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.airport_software.coordinator'`

- [ ] **Step 3: Write the implementation**

```python
# custom_components/airport_software/coordinator.py
"""DataUpdateCoordinator for airport-software."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import AirportSoftwareClient, InvalidAuth
from .const import DOMAIN, POLL_INTERVAL_SECONDS
from .models import AircraftStatus

_LOGGER = logging.getLogger(__name__)


class AirportSoftwareCoordinator(DataUpdateCoordinator[dict[str, AircraftStatus]]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry | None,
        client: AirportSoftwareClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=POLL_INTERVAL_SECONDS),
        )
        self.config_entry = entry
        self._client = client

    async def _async_update_data(self) -> dict[str, AircraftStatus]:
        try:
            statuses = await self._client.async_get_status()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(
                "airport-software rejected the configured credentials"
            ) from err
        except Exception as err:  # network or parse errors: retry next interval
            raise UpdateFailed(f"error communicating with airport-software: {err}") from err
        return {status.tail_number: status for status in statuses}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_coordinator.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/coordinator.py tests/test_coordinator.py
git commit -m "feat: add coordinator that stops polling on invalid auth"
```

---

## Task 8: Config flow

**Files:**
- Create: `custom_components/airport_software/config_flow.py`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `AirportSoftwareClient`, `InvalidAuth` (Task 6); `DOMAIN`, `CONF_BASE_URL`, `CONF_USERNAME`, `CONF_PASSWORD` (Task 1).
- Produces: `ConfigFlow` registered for `DOMAIN` — Task 9 (`__init__.py`) reads `entry.data[CONF_BASE_URL]` etc. that this flow creates.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config_flow.py
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.airport_software.client import InvalidAuth
from custom_components.airport_software.const import DOMAIN

USER_INPUT = {
    "base_url": "https://example.test",
    "username": "1234",
    "password": "secret",
}


async def test_user_flow_creates_entry_on_success(hass):
    with patch(
        "custom_components.airport_software.config_flow.AirportSoftwareClient.async_get_status",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == USER_INPUT


async def test_user_flow_shows_invalid_auth_error(hass):
    with patch(
        "custom_components.airport_software.config_flow.AirportSoftwareClient.async_get_status",
        side_effect=InvalidAuth("bad password"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
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
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config_flow.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.airport_software.config_flow'`

- [ ] **Step 3: Write the implementation**

```python
# custom_components/airport_software/config_flow.py
"""Config flow for airport-software."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .client import AirportSoftwareClient, InvalidAuth
from .const import CONF_BASE_URL, CONF_PASSWORD, CONF_USERNAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def _async_validate(data: dict[str, Any]) -> None:
    """Raise InvalidAuth or ConnectionError if the credentials don't work."""
    async with aiohttp.ClientSession() as session:
        client = AirportSoftwareClient(
            session, data[CONF_BASE_URL], data[CONF_USERNAME], data[CONF_PASSWORD]
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
                await _async_validate(user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001 - any other failure is "can't connect"
                _LOGGER.exception("Unexpected error validating airport-software login")
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_BASE_URL], data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config_flow.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/config_flow.py tests/test_config_flow.py
git commit -m "feat: add config flow with validation and reauth"
```

---

## Task 9: Integration setup (`__init__.py`)

**Files:**
- Create: `custom_components/airport_software/__init__.py`
- Test: `tests/test_init.py`

**Interfaces:**
- Consumes: `AirportSoftwareClient` (Task 6), `AirportSoftwareCoordinator` (Task 7), `DOMAIN`/`CONF_*` (Task 1).
- Produces: `async_setup_entry`, `async_unload_entry`; `hass.data[DOMAIN][entry.entry_id]` dict with keys `"coordinator"` and `"session"` — Tasks 10–11 (`binary_sensor.py`, `sensor.py`) read `hass.data[DOMAIN][entry.entry_id]["coordinator"]` in their `async_setup_entry`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_init.py
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.airport_software.const import DOMAIN
from custom_components.airport_software.models import AircraftStatus

ENTRY_DATA = {
    "base_url": "https://example.test",
    "username": "1234",
    "password": "secret",
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
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    assert coordinator.data == {"D-ABCD": status}


async def test_unload_entry_closes_session(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.airport_software.client.AirportSoftwareClient.async_get_status",
        return_value=[],
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    session = hass.data[DOMAIN][entry.entry_id]["session"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert session.closed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_init.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.airport_software'` (no `__init__.py` yet)

- [ ] **Step 3: Write the implementation**

```python
# custom_components/airport_software/__init__.py
"""The airport-software integration."""
from __future__ import annotations

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .client import AirportSoftwareClient
from .const import CONF_BASE_URL, CONF_PASSWORD, CONF_USERNAME, DOMAIN
from .coordinator import AirportSoftwareCoordinator

PLATFORMS = ["binary_sensor", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # A dedicated session (not HA's shared one) so this integration's
    # authenticated cookies never mix with other integrations' requests
    # to the same or other hosts.
    session = aiohttp.ClientSession()
    client = AirportSoftwareClient(
        session=session,
        base_url=entry.data[CONF_BASE_URL],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )
    coordinator = AirportSoftwareCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator, "session": session}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["session"].close()
    return unload_ok
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_init.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/__init__.py tests/test_init.py
git commit -m "feat: wire up integration setup/unload with dedicated session"
```

---

## Task 10: Binary sensor platform

**Files:**
- Create: `custom_components/airport_software/binary_sensor.py`
- Test: `tests/test_binary_sensor.py`

**Interfaces:**
- Consumes: `AirportSoftwareCoordinator` (Task 7), `hass.data[DOMAIN][entry.entry_id]["coordinator"]` (Task 9).
- Produces: nothing consumed by later tasks (leaf platform).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_binary_sensor.py
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.airport_software.const import DOMAIN
from custom_components.airport_software.models import AircraftStatus

ENTRY_DATA = {
    "base_url": "https://example.test",
    "username": "1234",
    "password": "secret",
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
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_binary_sensor.py -v`
Expected: FAIL — `state` is `None` (no `binary_sensor.py` platform registered yet)

- [ ] **Step 3: Write the implementation**

```python
# custom_components/airport_software/binary_sensor.py
"""Binary sensor platform for airport-software."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AirportSoftwareCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AirportSoftwareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        AirportSoftwareInUseBinarySensor(coordinator, tail_number)
        for tail_number in coordinator.data
    )


class AirportSoftwareInUseBinarySensor(
    CoordinatorEntity[AirportSoftwareCoordinator], BinarySensorEntity
):
    _attr_has_entity_name = True
    _attr_translation_key = "in_use"

    def __init__(self, coordinator: AirportSoftwareCoordinator, tail_number: str) -> None:
        super().__init__(coordinator)
        self._tail_number = tail_number
        self._attr_unique_id = f"{tail_number}_in_use"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, tail_number)},
            name=tail_number,
            manufacturer="airport-software DS GmbH",
        )

    @property
    def is_on(self) -> bool | None:
        status = self.coordinator.data.get(self._tail_number)
        return status.in_use if status else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_binary_sensor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/binary_sensor.py tests/test_binary_sensor.py
git commit -m "feat: add in_use binary sensor per aircraft"
```

---

## Task 11: Sensor platform

**Files:**
- Create: `custom_components/airport_software/sensor.py`
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes: `AirportSoftwareCoordinator` (Task 7), `hass.data[DOMAIN][entry.entry_id]["coordinator"]` (Task 9).
- Produces: nothing consumed by later tasks (leaf platform).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sensor.py
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.airport_software.const import DOMAIN
from custom_components.airport_software.models import AircraftStatus

ENTRY_DATA = {
    "base_url": "https://example.test",
    "username": "1234",
    "password": "secret",
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
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    condition_state = hass.states.get("sensor.d_abcd_condition")
    assert condition_state.state == "maintenance"
    assert condition_state.attributes["open_info_count"] == 2
    assert condition_state.attributes["remarks"] == "Engine work."

    hours_state = hass.states.get("sensor.d_abcd_remaining_hours")
    assert hours_state.state == "-1.5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sensor.py -v`
Expected: FAIL — both states are `None` (no `sensor.py` platform registered yet)

- [ ] **Step 3: Write the implementation**

```python
# custom_components/airport_software/sensor.py
"""Sensor platform for airport-software."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AirportSoftwareCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AirportSoftwareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = []
    for tail_number in coordinator.data:
        entities.append(AirportSoftwareConditionSensor(coordinator, tail_number))
        entities.append(AirportSoftwareRemainingHoursSensor(coordinator, tail_number))
    async_add_entities(entities)


def _device_info(tail_number: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, tail_number)},
        name=tail_number,
        manufacturer="airport-software DS GmbH",
    )


class AirportSoftwareConditionSensor(
    CoordinatorEntity[AirportSoftwareCoordinator], SensorEntity
):
    _attr_has_entity_name = True
    _attr_translation_key = "condition"

    def __init__(self, coordinator: AirportSoftwareCoordinator, tail_number: str) -> None:
        super().__init__(coordinator)
        self._tail_number = tail_number
        self._attr_unique_id = f"{tail_number}_condition"
        self._attr_device_info = _device_info(tail_number)

    @property
    def native_value(self) -> str | None:
        status = self.coordinator.data.get(self._tail_number)
        return status.condition if status else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        status = self.coordinator.data.get(self._tail_number)
        if not status:
            return {}
        return {"open_info_count": status.open_info_count, "remarks": status.remarks}


class AirportSoftwareRemainingHoursSensor(
    CoordinatorEntity[AirportSoftwareCoordinator], SensorEntity
):
    _attr_has_entity_name = True
    _attr_translation_key = "remaining_hours"
    _attr_native_unit_of_measurement = "h"

    def __init__(self, coordinator: AirportSoftwareCoordinator, tail_number: str) -> None:
        super().__init__(coordinator)
        self._tail_number = tail_number
        self._attr_unique_id = f"{tail_number}_remaining_hours"
        self._attr_device_info = _device_info(tail_number)

    @property
    def native_value(self) -> float | None:
        status = self.coordinator.data.get(self._tail_number)
        return status.remaining_hours if status else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_sensor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/sensor.py tests/test_sensor.py
git commit -m "feat: add condition and remaining-hours sensors per aircraft"
```

---

## Task 12: Full test suite, translations sensor keys, and README

**Files:**
- Modify: `custom_components/airport_software/strings.json`
- Modify: `custom_components/airport_software/translations/en.json`
- Create: `README.md`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing (final documentation/polish task).

- [ ] **Step 1: Add entity translation keys to `strings.json` and `translations/en.json`**

Add this top-level key to both files (alongside the existing `"config"` key from Task 1):

```json
  "entity": {
    "binary_sensor": {
      "in_use": {
        "name": "In use"
      }
    },
    "sensor": {
      "condition": {
        "name": "Condition"
      },
      "remaining_hours": {
        "name": "Remaining hours"
      }
    }
  }
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: all tests pass (Tasks 2–11's tests, ~24 tests total)

- [ ] **Step 3: Write `README.md`**

```markdown
# airport-software Home Assistant Integration

Reports aircraft status from an [airport-software](https://www.airport-software.com)
reservation system instance into Home Assistant.

## What you get

Per aircraft (one HA device per tail number):

- `binary_sensor.<tail>_in_use` — on when the aircraft's key is checked out
- `sensor.<tail>_condition` — `ready` or `maintenance`, with `open_info_count`
  and `remarks` attributes
- `sensor.<tail>_remaining_hours` — hours remaining to the next inspection
  (can be negative if overdue)

Polled every 15 minutes.

## Installation

Via HACS: add this repository as a custom repository, install
"airport-software", restart Home Assistant, then add the integration via
Settings → Devices & Services and enter your club's base URL, member
number, and password.

## A note on credentials

This integration logs in with your real member credentials on every
re-authentication. **Repeated failed logins can lock your account** — the
integration is designed to stop polling immediately (and prompt you to
re-enter your password) on the very first rejected login, rather than
retrying, but you should still double check your credentials carefully
when first setting this up.

## Manual verification (not part of the automated test suite)

Automated tests never perform a live login, to avoid any risk of locking a
real account. Before relying on this integration, verify once by hand:

1. Configure the integration with your real base URL, member number, and
   password.
2. Confirm entities appear for each aircraft and their values match what
   you see on the site's own booking overview page.
```

- [ ] **Step 4: Commit**

```bash
git add custom_components/airport_software/strings.json custom_components/airport_software/translations/en.json README.md
git commit -m "docs: add entity translations and README"
```
