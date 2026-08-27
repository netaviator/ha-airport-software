# airport-software Home Assistant Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a HACS-installable Home Assistant custom integration that logs into an airport-software reservation system instance and reports each aircraft's status (in-use, condition, remaining hours, remarks) as entities, polled every 15 minutes — plus an optional, configurable "free for the rest of the day" metric per aircraft.

**Architecture:** A `custom_components/airport_software/` package: pure-function HTML parsing (`parsing.py`), a stateful `aiohttp`-based client that replicates the validated ASP.NET WebForms login postback and optionally fetches a second page for today's availability (`client.py`), a `DataUpdateCoordinator` (`coordinator.py`) that turns client errors into either a hard auth-failure stop or a soft retry, a `ConfigFlow` for setup/reauth, and `binary_sensor`/`sensor` platforms.

**Tech Stack:** Python 3.13, Home Assistant custom integration APIs (`homeassistant.helpers.update_coordinator`, `homeassistant.config_entries`), `aiohttp` for HTTP, `pytest` + `pytest-asyncio` + `aioresponses` for client/parsing tests, `pytest-homeassistant-custom-component` for coordinator/config-flow/entity tests.

**Spec:** `docs/superpowers/specs/2026-08-27-airport-software-integration-design.md`

## Global Constraints

- No automated test ever performs a live login against a real airport-software instance — all HTTP is mocked (`aioresponses`) or fixture-driven, per the spec's lockout-risk finding.
- On the client detecting rejected credentials, raise `InvalidAuth` — the coordinator must convert this to `ConfigEntryAuthFailed`, which stops automatic polling entirely (no retry loop against the real site).
- Login POST must set `__EVENTTARGET=ctl00$MainContentPlaceHolder$cmdLogin` and `__EVENTARGUMENT=""`, and must NOT include a `ctl00$MainContentPlaceHolder$cmdLogin` field (validated finding from the spec's Background section).
- Base URL, member number, and password are all user-configurable via the config flow (generic, HACS-shareable — not hardcoded to any one club).
- The free-rest-of-day feature is optional: a config-flow toggle (`enable_free_rest_of_day`, default on) and a configurable cutoff time (`free_rest_of_day_cutoff`, default `"18:00"`, `HH:MM` format) — never a hardcoded 18:00 in the logic.
- Follow immutability style: `AircraftStatus` is a frozen dataclass; no in-place mutation of it (use `dataclasses.replace` to merge in flynow data).

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

**Interfaces:**
- Produces: `DOMAIN = "airport_software"`, `POLL_INTERVAL_SECONDS = 900`, `CONF_BASE_URL = "base_url"`, `CONF_USERNAME = "username"`, `CONF_PASSWORD = "password"`, `CONF_ENABLE_FREE_REST_OF_DAY = "enable_free_rest_of_day"`, `CONF_FREE_REST_OF_DAY_CUTOFF = "free_rest_of_day_cutoff"`, `DEFAULT_FREE_REST_OF_DAY_CUTOFF = "18:00"`, `CONF_ENABLE_TOWER_DUTY = "enable_tower_duty"`, `CONF_ENABLE_QUALIFICATION_STATUS = "enable_qualification_status"` — every later task imports these from `const.py`.

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
CONF_ENABLE_FREE_REST_OF_DAY = "enable_free_rest_of_day"
CONF_FREE_REST_OF_DAY_CUTOFF = "free_rest_of_day_cutoff"
CONF_ENABLE_TOWER_DUTY = "enable_tower_duty"
CONF_ENABLE_QUALIFICATION_STATUS = "enable_qualification_status"

DEFAULT_FREE_REST_OF_DAY_CUTOFF = "18:00"
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
          "password": "Password",
          "enable_free_rest_of_day": "Report \"free for the rest of the day\"",
          "free_rest_of_day_cutoff": "Cutoff time (HH:MM) — ignore availability starting later than this",
          "enable_tower_duty": "Report who's currently on tower (Flugleitung) duty",
          "enable_qualification_status": "Report your next-expiring qualification/license item"
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
      "cannot_connect": "Could not reach the site. Check the base URL.",
      "invalid_cutoff_format": "Cutoff time must be in HH:MM format, e.g. 18:00."
    },
    "abort": {
      "reauth_successful": "Re-authentication was successful."
    }
  },
  "entity": {
    "binary_sensor": {
      "in_use": {
        "name": "In use"
      },
      "free_rest_of_day": {
        "name": "Free rest of day"
      }
    },
    "sensor": {
      "condition": {
        "name": "Condition"
      },
      "remaining_hours": {
        "name": "Remaining hours"
      },
      "tower_duty_now": {
        "name": "Tower duty now"
      },
      "next_expiring_qualification": {
        "name": "Next expiring qualification"
      }
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
- Produces: `AircraftStatus` frozen dataclass with fields `tail_number: str`, `in_use: bool`, `condition: Literal["ready", "maintenance"]`, `open_info_count: int`, `remaining_hours: float`, `remarks: str`, `available_from_today: str | None = None`, `free_rest_of_day: bool = False`. Every later task (`parsing.py`, `client.py`, `coordinator.py`, `sensor.py`, `binary_sensor.py`) imports this exact type. The last two fields default to "unknown" because the base overview parser has no way to know them — only the optional flynow merge in `client.py` fills them in.

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


def test_aircraft_status_defaults_flynow_fields_to_unknown():
    status = AircraftStatus(
        tail_number="D-ABCD",
        in_use=False,
        condition="ready",
        open_info_count=0,
        remaining_hours=82.083,
        remarks="All good.",
    )
    assert status.available_from_today is None
    assert status.free_rest_of_day is False


def test_aircraft_status_accepts_explicit_flynow_fields():
    status = AircraftStatus(
        tail_number="D-ABCD",
        in_use=False,
        condition="ready",
        open_info_count=0,
        remaining_hours=82.083,
        remarks="All good.",
        available_from_today="immediate",
        free_rest_of_day=True,
    )
    assert status.available_from_today == "immediate"
    assert status.free_rest_of_day is True
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
    available_from_today: str | None = None
    free_rest_of_day: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/models.py tests/test_models.py
git commit -m "feat: add AircraftStatus data model with optional flynow fields"
```

---

## Task 3: Login field extraction

**Files:**
- Create: `custom_components/airport_software/parsing.py`
- Create: `tests/fixtures/login_page.html`
- Test: `tests/test_parsing_login.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `extract_hidden_fields(html: str) -> dict[str, str]` — Task 6 (`client.py`) calls this on the login page GET response.

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
- Produces: `login_failed(response_html: str) -> bool` — Task 6 (`client.py`) calls this on the login POST response to decide whether to raise `InvalidAuth`.

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
- Produces: `parse_status_table(page_html: str) -> list[AircraftStatus]` — Task 6 (`client.py`) calls this on the overview page GET response. Every `AircraftStatus` it returns keeps `available_from_today=None` and `free_rest_of_day=False` (this parser only ever sees `booking_overview.aspx`, which has no flynow data).

- [ ] **Step 1: Create the fixture**

This reproduces the real page's structure, including the tooltip `onmouseover` attribute containing literal (unescaped) `<p>` tags inside a JS string — a real quirk from the live site that breaks naive "strip all `<...>`" parsing, so the parser must extract the remaining-hours value with a targeted digit pattern instead of generic tag-stripping. It uses four tail numbers (`D-ABCD`, `D-EFGH`, `D-IJKL`, `D-MNOP`) that Task 7's flynow fixture deliberately reuses (with one, `D-MNOP`, omitted there) to test the cross-page merge.

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
import pytest

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
    assert d_abcd.available_from_today is None
    assert d_abcd.free_rest_of_day is False


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

## Task 6: Today's availability parsing (flynow)

**Files:**
- Modify: `custom_components/airport_software/parsing.py`
- Create: `tests/fixtures/booking_flynow.html`
- Test: `tests/test_parsing_flynow.py`

**Interfaces:**
- Consumes: nothing new (reuses `_ROW_RE`, `_CELL_RE`, `_strip_tags` already defined in `parsing.py` from Task 5).
- Produces: `parse_flynow_table(page_html: str, cutoff: str = "18:00") -> dict[str, tuple[str, bool]]` mapping `tail_number -> (available_from_today, free_rest_of_day)` for aircraft that appear in the table. A tail number absent from the result means "no open slot today" — callers must treat a missing key as `(None, False)`. Task 7 (`client.py`) calls this and merges the result into `AircraftStatus` list via `dataclasses.replace`.

- [ ] **Step 1: Create the fixture**

Reuses three of the four tail numbers from `tests/fixtures/booking_overview.html` (`D-ABCD`, `D-EFGH`, `D-IJKL`), deliberately omitting `D-MNOP` so Task 7's merge test can verify the "absent from flynow" default. Adds one extra tail number, `D-QRST` (not present in the overview fixture — only used here, in isolation, to cover the "available only until a specific time today" case), because that case doesn't need to be exercised in the cross-page merge test.

```html
<!-- tests/fixtures/booking_flynow.html -->
<html><body>
<form name="aspnetForm" method="post" action="./booking_flynow.aspx" id="aspnetForm">
<div id="ctl00_MainContentPlaceHolder_divBookingList"><table width="100%"><colgroup><col width="90"><col width="120"><col width="120"></colgroup><tr><th>Rufzeichen</th><th>Verf&uuml;gbar ab</th><th>Verf&uuml;gbar bis</th><th>Info</th></tr><tr><td><a href="#" onclick="link('booking_new.aspx?link=1');">D-ABCD</a></td><td>Sofort</td><td>Ende des Tages</td><td></td></tr><tr><td><a href="#" onclick="link('booking_new.aspx?link=2');">D-EFGH</a></td><td>17:30</td><td>Ende des Tages</td><td>Ausgeliehen von Mustermann bis 17:30</td></tr><tr><td><a href="#" onclick="link('booking_new.aspx?link=3');">D-IJKL</a></td><td>20:00</td><td>Ende des Tages</td><td></td></tr><tr><td><a href="#" onclick="link('booking_new.aspx?link=4');">D-QRST</a></td><td>15:00</td><td>17:00</td><td>N&auml;chste Reservierung ab 17:00</td></tr></table></div>
</form>
</body></html>
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_parsing_flynow.py
from tests.conftest import load_fixture
from custom_components.airport_software.parsing import parse_flynow_table


def test_parse_flynow_table_immediate_and_free_until_eod_is_free():
    html = load_fixture("booking_flynow.html")
    result = parse_flynow_table(html, cutoff="18:00")
    assert result["D-ABCD"] == ("immediate", True)


def test_parse_flynow_table_before_cutoff_and_free_until_eod_is_free():
    html = load_fixture("booking_flynow.html")
    result = parse_flynow_table(html, cutoff="18:00")
    assert result["D-EFGH"] == ("17:30", True)


def test_parse_flynow_table_after_cutoff_is_not_free():
    html = load_fixture("booking_flynow.html")
    result = parse_flynow_table(html, cutoff="18:00")
    assert result["D-IJKL"] == ("20:00", False)


def test_parse_flynow_table_specific_end_time_is_not_free_rest_of_day():
    """A later booking today (bis != end of day) means it's not free for
    the *rest* of the day, even though the from-time is early."""
    html = load_fixture("booking_flynow.html")
    result = parse_flynow_table(html, cutoff="18:00")
    assert result["D-QRST"] == ("15:00", False)


def test_parse_flynow_table_respects_custom_cutoff():
    html = load_fixture("booking_flynow.html")
    result = parse_flynow_table(html, cutoff="20:30")
    assert result["D-IJKL"] == ("20:00", True)


def test_parse_flynow_table_omits_fully_booked_aircraft():
    html = load_fixture("booking_flynow.html")
    result = parse_flynow_table(html, cutoff="18:00")
    assert "D-MNOP" not in result
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_parsing_flynow.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_flynow_table'`

- [ ] **Step 4: Write the implementation**

```python
# custom_components/airport_software/parsing.py (append)
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_parsing_flynow.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Commit**

```bash
git add custom_components/airport_software/parsing.py tests/fixtures/booking_flynow.html tests/test_parsing_flynow.py
git commit -m "feat: parse today's-availability table with configurable cutoff"
```

---

## Task 7: HTTP client

**Files:**
- Create: `custom_components/airport_software/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `extract_hidden_fields`, `login_failed`, `parse_status_table`, `parse_flynow_table` (Tasks 3–6); `AircraftStatus` (Task 2).
- Produces: `AirportSoftwareClient(session, base_url, username, password, enable_free_rest_of_day=True, free_rest_of_day_cutoff="18:00")` with `async def async_get_status(self) -> list[AircraftStatus]`, and `InvalidAuth` exception — Task 8 (`coordinator.py`) constructs and calls this; Task 9 (`config_flow.py`) also constructs one for setup validation.

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
FLYNOW_URL = f"{BASE_URL}/internal/booking_flynow.aspx"


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.airport_software.client'`

- [ ] **Step 3: Write the implementation**

```python
# custom_components/airport_software/client.py
"""Stateful HTTP client for an airport-software instance."""
from __future__ import annotations

from dataclasses import replace

import aiohttp

from .parsing import extract_hidden_fields, login_failed, parse_flynow_table, parse_status_table
from .models import AircraftStatus

_LOGIN_PATH = "/login/login.aspx"
_OVERVIEW_PATH = "/internal/booking_overview.aspx"
_FLYNOW_PATH = "/internal/booking_flynow.aspx"
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

        overview_html, flynow_html = await self._async_fetch_pages()
        if self._looks_like_login_page(overview_html) or (
            flynow_html is not None and self._looks_like_login_page(flynow_html)
        ):
            await self._async_login()
            overview_html, flynow_html = await self._async_fetch_pages()

        statuses = parse_status_table(overview_html)
        if not self._enable_free_rest_of_day:
            return statuses

        flynow_data = parse_flynow_table(flynow_html, cutoff=self._free_rest_of_day_cutoff)
        return [
            replace(
                status,
                available_from_today=flynow_data.get(status.tail_number, (None, False))[0],
                free_rest_of_day=flynow_data.get(status.tail_number, (None, False))[1],
            )
            for status in statuses
        ]

    async def _async_fetch_pages(self) -> tuple[str, str | None]:
        overview_html = await self._async_fetch(_OVERVIEW_PATH)
        if not self._enable_free_rest_of_day:
            return overview_html, None
        flynow_html = await self._async_fetch(_FLYNOW_PATH)
        return overview_html, flynow_html

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_client.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/client.py tests/test_client.py
git commit -m "feat: add AirportSoftwareClient with optional flynow merge"
```

---

## Task 8: Coordinator

**Files:**
- Create: `custom_components/airport_software/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `AirportSoftwareClient`, `InvalidAuth` (Task 7); `AircraftStatus` (Task 2); `DOMAIN`, `POLL_INTERVAL_SECONDS` (Task 1).
- Produces: `AirportSoftwareCoordinator(hass, entry, client)` subclassing `DataUpdateCoordinator[dict[str, AircraftStatus]]` — Task 16 (`__init__.py`) constructs this; Tasks 17–18 (`binary_sensor.py`, `sensor.py`) read `coordinator.data`. (This coordinator only ever handles aircraft data — the tower-duty and qualification-status features added in Tasks 10–15 each get their own, separate coordinator, since neither is per-aircraft data.)

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

## Task 9: Config flow

**Files:**
- Create: `custom_components/airport_software/config_flow.py`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `AirportSoftwareClient`, `InvalidAuth` (Task 7); `DOMAIN`, `CONF_BASE_URL`, `CONF_USERNAME`, `CONF_PASSWORD`, `CONF_ENABLE_FREE_REST_OF_DAY`, `CONF_FREE_REST_OF_DAY_CUTOFF`, `DEFAULT_FREE_REST_OF_DAY_CUTOFF`, `CONF_ENABLE_TOWER_DUTY`, `CONF_ENABLE_QUALIFICATION_STATUS` (Task 1).
- Produces: `ConfigFlow` registered for `DOMAIN` — Task 16 (`__init__.py`) reads `entry.data[CONF_BASE_URL]` etc. that this flow creates, including the flynow keys, `CONF_ENABLE_TOWER_DUTY`, and `CONF_ENABLE_QUALIFICATION_STATUS` (all always present in stored entry data, since the schema fills in defaults for any field the user leaves untouched).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config_flow.py
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.airport_software.client import InvalidAuth
from custom_components.airport_software.const import (
    CONF_ENABLE_FREE_REST_OF_DAY,
    CONF_ENABLE_QUALIFICATION_STATUS,
    CONF_ENABLE_TOWER_DUTY,
    CONF_FREE_REST_OF_DAY_CUTOFF,
    DOMAIN,
)

REQUIRED_INPUT = {
    "base_url": "https://example.test",
    "username": "1234",
    "password": "secret",
}


async def test_user_flow_creates_entry_with_flynow_defaults():
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


async def test_user_flow_accepts_explicit_flynow_settings():
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


async def test_user_flow_rejects_malformed_cutoff():
    user_input = {**REQUIRED_INPUT, "free_rest_of_day_cutoff": "not-a-time"}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_cutoff_format"}


async def test_user_flow_shows_invalid_auth_error():
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


async def test_user_flow_shows_cannot_connect_error():
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
```

Every test function above takes `hass` as its first parameter (the `pytest-homeassistant-custom-component` fixture) — add `hass` as a parameter to each `async def test_...(hass):` when transcribing these into the file; it's omitted from the snippets above only to keep them shorter to read, but every one of these tests calls `hass.config_entries...` so every signature must include it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config_flow.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.airport_software.config_flow'`

- [ ] **Step 3: Write the implementation**

```python
# custom_components/airport_software/config_flow.py
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


STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_ENABLE_FREE_REST_OF_DAY, default=True): bool,
        vol.Optional(
            CONF_FREE_REST_OF_DAY_CUTOFF, default=DEFAULT_FREE_REST_OF_DAY_CUTOFF
        ): _validate_cutoff,
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
                data = STEP_USER_SCHEMA(user_input)
            except vol.Invalid:
                errors["base"] = "invalid_cutoff_format"
            else:
                try:
                    await _async_validate(data)
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except Exception:  # noqa: BLE001 - anything else is "can't connect"
                    _LOGGER.exception("Unexpected error validating airport-software login")
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(title=data[CONF_BASE_URL], data=data)

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config_flow.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/config_flow.py tests/test_config_flow.py
git commit -m "feat: add config flow with optional configurable flynow settings"
```

---

## Task 10: Tower duty data model + parsing

**Files:**
- Modify: `custom_components/airport_software/models.py`
- Modify: `custom_components/airport_software/parsing.py`
- Create: `tests/fixtures/kalender.html`
- Test: `tests/test_parsing_tower_duty.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `TowerDutyStatus` frozen dataclass (`on_duty: str | None`, `note: str | None = None`); `parse_tower_duty(page_html: str, now: datetime.datetime) -> TowerDutyStatus | None` — Task 11 (`client.py`) calls this on the `kalender.aspx` GET response. Returns `None` if today's date isn't present in the fetched page at all (distinct from a `TowerDutyStatus(on_duty=None)`, which means today is present but no shift covers this exact time).

- [ ] **Step 1: Add the model**

```python
# custom_components/airport_software/models.py (append)
@dataclass(frozen=True)
class TowerDutyStatus:
    on_duty: str | None
    note: str | None = None
```

- [ ] **Step 2: Create the fixture**

Uses fake names (not real club members). Reproduces the real page's tooltip quirk (literal unescaped `<p>` tags inside the `onmouseover` JS string) on the second shift's name cell, same as the remaining-hours cell in `booking_overview.html`.

```html
<!-- tests/fixtures/kalender.html -->
<html><body>
<form name="aspnetForm" method="post" action="./kalender.aspx" id="aspnetForm">
<h2><span id="ctl00_siteheader" class="kopf">Kalender: Flugleitung Januar 2026</span></h2>
<select name="ctl00$MainContentPlaceHolder$lstKalender" id="ctl00_MainContentPlaceHolder_lstKalender">
<option selected="selected" value="FLUGLTG">Flugleitung</option>
</select>
<div id="ctl00_MainContentPlaceHolder_divKalenderList"><table width="100%"><colgroup><col width="60"><col width="90"><col width="140"><col width="90"><col width="140"></colgroup><tr><th class="grid_leftalign">Mi, 14</th><td><a href="#" onclick="link('kalender_maint.aspx?link=1');">08:00 - 12:00</a></td><td>Mustermann, Erika</td><td><a href="#" onclick="link('kalender_maint.aspx?link=2');">12:00 - 20:00</a></td><td>Beispiel, Max  <a class="stdlink_tooltip" onmouseover="return(showTip('<p class=\'boxhead\'>Information</p><p class=\'boxcontent\'>bis 18:00</p>'));" onmouseout="hideTip();"><img src="/style/design/info.png" alt="" height="15px" width="15px" /></a></td></tr></table></div>
</form>
</body></html>
```

- [ ] **Step 3: Write the failing tests**

```python
# tests/test_parsing_tower_duty.py
import datetime as dt

from tests.conftest import load_fixture
from custom_components.airport_software.parsing import parse_tower_duty


def test_parse_tower_duty_returns_person_for_first_shift():
    html = load_fixture("kalender.html")
    result = parse_tower_duty(html, dt.datetime(2026, 1, 14, 10, 0))
    assert result.on_duty == "Mustermann, Erika"
    assert result.note is None


def test_parse_tower_duty_returns_person_and_note_for_second_shift():
    html = load_fixture("kalender.html")
    result = parse_tower_duty(html, dt.datetime(2026, 1, 14, 15, 0))
    assert result.on_duty == "Beispiel, Max"
    assert result.note == "bis 18:00"


def test_parse_tower_duty_no_coverage_outside_shifts():
    html = load_fixture("kalender.html")
    result = parse_tower_duty(html, dt.datetime(2026, 1, 14, 23, 0))
    assert result.on_duty is None
    assert result.note is None


def test_parse_tower_duty_returns_none_when_date_not_in_page():
    html = load_fixture("kalender.html")
    assert parse_tower_duty(html, dt.datetime(2026, 1, 16, 10, 0)) is None
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_parsing_tower_duty.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_tower_duty'`

- [ ] **Step 5: Write the implementation**

First, update the existing models import line near the top of `parsing.py` (added in Task 5) to also import `TowerDutyStatus`:

```python
# custom_components/airport_software/parsing.py — change this existing line:
#   from .models import AircraftStatus
# to:
from .models import AircraftStatus, TowerDutyStatus
```

Then append:

```python
# custom_components/airport_software/parsing.py (append)
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_parsing_tower_duty.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: Commit**

```bash
git add custom_components/airport_software/models.py custom_components/airport_software/parsing.py \
  tests/fixtures/kalender.html tests/test_parsing_tower_duty.py
git commit -m "feat: parse who's on Flugleitung (tower) duty right now"
```

---

## Task 11: Tower duty client method

**Files:**
- Modify: `custom_components/airport_software/client.py`
- Create: `tests/fixtures/kalender_wrong_type.html`
- Test: `tests/test_client.py` (append)

**Interfaces:**
- Consumes: `parse_tower_duty`, `extract_hidden_fields` (Task 10, Task 3); `TowerDutyStatus` (Task 10).
- Produces: `AirportSoftwareClient.async_get_tower_duty(self, now: datetime.datetime) -> TowerDutyStatus | None` — Task 12 (`coordinator.py`) calls this.

- [ ] **Step 1: Create the fixture for "wrong calendar type selected"**

Represents the page when the user's session last had a *different* calendar type selected (e.g. "Konferenzraum") — the client must detect this and switch to Flugleitung via postback before parsing.

```html
<!-- tests/fixtures/kalender_wrong_type.html -->
<html><body>
<form name="aspnetForm" method="post" action="./kalender.aspx" id="aspnetForm">
<input type="hidden" name="__EVENTTARGET" id="__EVENTTARGET" value="" />
<input type="hidden" name="__EVENTARGUMENT" id="__EVENTARGUMENT" value="" />
<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="FAKEVIEWSTATE789==" />
<input type="hidden" name="__VIEWSTATEGENERATOR" id="__VIEWSTATEGENERATOR" value="26F4C21C" />
<input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="FAKEEVENTVALIDATION3==" />
<h2><span id="ctl00_siteheader" class="kopf">Kalender: Konferenzraum Januar 2026</span></h2>
<select name="ctl00$MainContentPlaceHolder$lstKalender" id="ctl00_MainContentPlaceHolder_lstKalender">
<option selected="selected" value="CONF1">Konferenzraum</option>
<option value="FLUGLTG">Flugleitung</option>
</select>
</form>
</body></html>
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_client.py (append)
import datetime as dt

from custom_components.airport_software.models import TowerDutyStatus

KALENDER_URL = f"{BASE_URL}/internal/kalender.aspx"


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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_client.py -v -k tower_duty`
Expected: FAIL with `AttributeError: 'AirportSoftwareClient' object has no attribute 'async_get_tower_duty'`

- [ ] **Step 4: Write the implementation**

Update the existing imports near the top of `client.py`:

```python
# custom_components/airport_software/client.py — add to the existing import block:
import datetime as dt

from .parsing import parse_tower_duty  # alongside the existing parsing imports
from .models import TowerDutyStatus  # alongside the existing models import
```

Add these two module-level constants near the other `_..._PATH` constants:

```python
# custom_components/airport_software/client.py
_KALENDER_PATH = "/internal/kalender.aspx"
_FLUGLTG_SELECTED_MARKER = 'selected="selected" value="FLUGLTG"'
```

Add these two methods inside the `AirportSoftwareClient` class:

```python
    async def async_get_tower_duty(self, now: dt.datetime) -> TowerDutyStatus | None:
        if self._auth_failed:
            raise InvalidAuth("airport-software previously rejected these credentials")
        if not self._authenticated:
            await self._async_login()

        page_html = await self._async_fetch(_KALENDER_PATH)
        if self._looks_like_login_page(page_html):
            await self._async_login()
            page_html = await self._async_fetch(_KALENDER_PATH)

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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_client.py -v -k tower_duty`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add custom_components/airport_software/client.py tests/fixtures/kalender_wrong_type.html tests/test_client.py
git commit -m "feat: add tower duty fetch with calendar-type-switch handling"
```

---

## Task 12: Tower duty coordinator

**Files:**
- Modify: `custom_components/airport_software/coordinator.py`
- Test: `tests/test_coordinator.py` (append)

**Interfaces:**
- Consumes: `AirportSoftwareClient.async_get_tower_duty` (Task 11); `TowerDutyStatus` (Task 10); `DOMAIN`, `POLL_INTERVAL_SECONDS` (Task 1).
- Produces: `TowerDutyCoordinator(hass, entry, client)` subclassing `DataUpdateCoordinator[TowerDutyStatus | None]` — Task 16 (`__init__.py`) constructs this; Task 18 (`sensor.py`) reads `coordinator.data`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_coordinator.py (append)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_coordinator.py -v -k tower_duty`
Expected: FAIL with `ImportError: cannot import name 'TowerDutyCoordinator'`

- [ ] **Step 3: Write the implementation**

Update the existing imports near the top of `coordinator.py` to add `dt_util` and `TowerDutyStatus`:

```python
# custom_components/airport_software/coordinator.py — add:
from homeassistant.util import dt as dt_util

from .models import AircraftStatus, TowerDutyStatus  # extends the existing models import
```

Append:

```python
# custom_components/airport_software/coordinator.py (append)
class TowerDutyCoordinator(DataUpdateCoordinator[TowerDutyStatus | None]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry | None,
        client: AirportSoftwareClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_tower_duty",
            update_interval=timedelta(seconds=POLL_INTERVAL_SECONDS),
        )
        self.config_entry = entry
        self._client = client

    async def _async_update_data(self) -> TowerDutyStatus | None:
        try:
            return await self._client.async_get_tower_duty(dt_util.now())
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(
                "airport-software rejected the configured credentials"
            ) from err
        except Exception as err:
            raise UpdateFailed(f"error communicating with airport-software: {err}") from err
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_coordinator.py -v -k tower_duty`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/coordinator.py tests/test_coordinator.py
git commit -m "feat: add TowerDutyCoordinator"
```

---

## Task 13: Qualification status data model + parsing

**Files:**
- Modify: `custom_components/airport_software/models.py`
- Modify: `custom_components/airport_software/parsing.py`
- Create: `tests/fixtures/mycode.html`
- Create: `tests/fixtures/mycode_never_expires_only.html`
- Test: `tests/test_parsing_qualification.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `QualificationStatus` frozen dataclass (`label: str | None`, `subcode: str | None`, `end_date: str | None` — ISO `"YYYY-MM-DD"` or `None`, `days_remaining: int | None`, `severity: Literal["ok", "info", "warning", "issue"]`); `parse_qualification_status(page_html: str, today: datetime.date) -> QualificationStatus | None` — Task 14 (`client.py`) calls this. Severity thresholds (fixed, not configurable — the user specified exact values): `days_remaining <= 30` → `"info"`, `<= 14` → `"warning"`, `< 0` (already past) → `"issue"`, otherwise (or never expires) → `"ok"`.

- [ ] **Step 1: Add the model**

`Literal` is already imported at the top of `models.py` (from Task 2) — no new import needed, just append:

```python
# custom_components/airport_software/models.py (append)
@dataclass(frozen=True)
class QualificationStatus:
    label: str | None
    subcode: str | None
    end_date: str | None
    days_remaining: int | None
    severity: Literal["ok", "info", "warning", "issue"]
```

- [ ] **Step 2: Create the fixtures**

Uses fake license data (not the real logged-in user's actual qualifications).

```html
<!-- tests/fixtures/mycode.html -->
<html><body>
<table cellspacing="0" rules="all" border="1" id="ctl00_MainContentPlaceHolder_grdAuswahl">
<caption>Meine Lizenzinformationen</caption>
<tr><th scope="col">Bezeichnung Code</th><th scope="col">Beginn</th><th scope="col">Ende</th><th scope="col">Bezeichnung SubCode</th><th scope="col">SubCode</th></tr>
<tr><td>Medical Class II</td><td>01.01.2026</td><td>20.03.2026</td><td>Medical Klasse 2</td><td>MEDICAL - CLASS II</td></tr>
<tr><td>Lizenz E-Klasse</td><td>01.01.2020</td><td>31.12.9999</td><td>Lizenz E-Klasse</td><td>F MOTOR L - OK</td></tr>
</table>
</body></html>
```

```html
<!-- tests/fixtures/mycode_never_expires_only.html -->
<html><body>
<table cellspacing="0" rules="all" border="1" id="ctl00_MainContentPlaceHolder_grdAuswahl">
<caption>Meine Lizenzinformationen</caption>
<tr><th scope="col">Bezeichnung Code</th><th scope="col">Beginn</th><th scope="col">Ende</th><th scope="col">Bezeichnung SubCode</th><th scope="col">SubCode</th></tr>
<tr><td>Lizenz E-Klasse</td><td>01.01.2020</td><td>31.12.9999</td><td>Lizenz E-Klasse</td><td>F MOTOR L - OK</td></tr>
</table>
</body></html>
```

- [ ] **Step 3: Write the failing tests**

```python
# tests/test_parsing_qualification.py
import datetime as dt

from tests.conftest import load_fixture
from custom_components.airport_software.models import QualificationStatus
from custom_components.airport_software.parsing import parse_qualification_status


def test_parse_qualification_status_ok_when_far_from_expiry():
    html = load_fixture("mycode.html")
    result = parse_qualification_status(html, today=dt.date(2026, 1, 1))
    assert result.label == "Medical Class II"
    assert result.days_remaining == 78
    assert result.severity == "ok"


def test_parse_qualification_status_info_within_30_days():
    html = load_fixture("mycode.html")
    result = parse_qualification_status(html, today=dt.date(2026, 2, 20))
    assert result.days_remaining == 28
    assert result.severity == "info"


def test_parse_qualification_status_warning_within_14_days():
    html = load_fixture("mycode.html")
    result = parse_qualification_status(html, today=dt.date(2026, 3, 6))
    assert result.days_remaining == 14
    assert result.severity == "warning"


def test_parse_qualification_status_issue_when_past_due():
    html = load_fixture("mycode.html")
    result = parse_qualification_status(html, today=dt.date(2026, 3, 25))
    assert result.days_remaining == -5
    assert result.severity == "issue"


def test_parse_qualification_status_ignores_never_expiring_entries():
    html = load_fixture("mycode_never_expires_only.html")
    result = parse_qualification_status(html, today=dt.date(2026, 1, 1))
    assert result == QualificationStatus(
        label=None, subcode=None, end_date=None, days_remaining=None, severity="ok"
    )


def test_parse_qualification_status_returns_none_when_table_missing():
    assert parse_qualification_status("<html></html>", today=dt.date(2026, 1, 1)) is None
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_parsing_qualification.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_qualification_status'`

- [ ] **Step 5: Write the implementation**

Update the existing models import line near the top of `parsing.py` (already extended once in Task 10) to also include `QualificationStatus`:

```python
# custom_components/airport_software/parsing.py — change this existing line:
#   from .models import AircraftStatus, TowerDutyStatus
# to:
from .models import AircraftStatus, QualificationStatus, TowerDutyStatus
```

Then append:

```python
# custom_components/airport_software/parsing.py (append)
_QUALIFICATION_TABLE_RE = re.compile(
    r'<table[^>]*id="ctl00_MainContentPlaceHolder_grdAuswahl"[^>]*>(.*?)</table>',
    re.DOTALL,
)
_NEVER_EXPIRES = dt.date(9999, 12, 31)
_INFO_THRESHOLD_DAYS = 30
_WARNING_THRESHOLD_DAYS = 14


def _parse_german_date(value: str) -> dt.date:
    day, month, year = value.split(".")
    return dt.date(int(year), int(month), int(day))


def _classify_severity(days_remaining: int | None) -> str:
    if days_remaining is None:
        return "ok"
    if days_remaining < 0:
        return "issue"
    if days_remaining <= _WARNING_THRESHOLD_DAYS:
        return "warning"
    if days_remaining <= _INFO_THRESHOLD_DAYS:
        return "info"
    return "ok"


def parse_qualification_status(page_html: str, today: dt.date) -> QualificationStatus | None:
    """The soonest-expiring (or already-expired) qualification/license item.

    Returns None if the qualification table isn't present in the page at
    all (parse failure). Returns a QualificationStatus with every field
    None (except severity="ok") if the table is present but every entry
    never expires (Ende == 31.12.9999).
    """
    table_match = _QUALIFICATION_TABLE_RE.search(page_html)
    if not table_match:
        return None

    candidates: list[tuple[dt.date, str, str]] = []
    for row in _ROW_RE.findall(table_match.group(1)):
        if "<th" in row:
            continue
        cells = _CELL_RE.findall(row)
        if len(cells) != 5:
            continue
        label = _strip_tags(cells[0])
        end_date = _parse_german_date(_strip_tags(cells[2]))
        subcode = _strip_tags(cells[4])
        if end_date == _NEVER_EXPIRES:
            continue
        candidates.append((end_date, label, subcode))

    if not candidates:
        return QualificationStatus(
            label=None, subcode=None, end_date=None, days_remaining=None, severity="ok"
        )

    end_date, label, subcode = min(candidates, key=lambda c: c[0])
    days_remaining = (end_date - today).days
    return QualificationStatus(
        label=label,
        subcode=subcode,
        end_date=end_date.isoformat(),
        days_remaining=days_remaining,
        severity=_classify_severity(days_remaining),
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_parsing_qualification.py -v`
Expected: PASS (6 passed)

- [ ] **Step 7: Commit**

```bash
git add custom_components/airport_software/models.py custom_components/airport_software/parsing.py \
  tests/fixtures/mycode.html tests/fixtures/mycode_never_expires_only.html tests/test_parsing_qualification.py
git commit -m "feat: parse next-expiring qualification with severity classification"
```

---

## Task 14: Qualification status client method

**Files:**
- Modify: `custom_components/airport_software/client.py`
- Test: `tests/test_client.py` (append)

**Interfaces:**
- Consumes: `parse_qualification_status` (Task 13); `QualificationStatus` (Task 13).
- Produces: `AirportSoftwareClient.async_get_next_expiring_qualification(self, today: datetime.date) -> QualificationStatus | None` — Task 15 (`coordinator.py`) calls this.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client.py (append)
MYCODE_URL = f"{BASE_URL}/internal/mycode.aspx"


async def test_async_get_next_expiring_qualification_returns_parsed_result():
    login_page = load_fixture("login_page.html")
    login_success = load_fixture("login_response_success.html")
    mycode_page = load_fixture("mycode.html")

    with aioresponses() as mocked:
        mocked.get(LOGIN_URL, body=login_page)
        mocked.post(LOGIN_URL, body=login_success)
        mocked.get(MYCODE_URL, body=mycode_page)

        async with aiohttp.ClientSession() as session:
            client = AirportSoftwareClient(session, BASE_URL, "1234", "secret")
            result = await client.async_get_next_expiring_qualification(dt.date(2026, 1, 1))

    assert result.label == "Medical Class II"
    assert result.severity == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_client.py -v -k qualification`
Expected: FAIL with `AttributeError: 'AirportSoftwareClient' object has no attribute 'async_get_next_expiring_qualification'`

- [ ] **Step 3: Write the implementation**

Update the existing imports near the top of `client.py`:

```python
# custom_components/airport_software/client.py — add to the existing import block:
from .parsing import parse_qualification_status  # alongside the existing parsing imports
from .models import QualificationStatus  # alongside the existing models import
```

Add this constant near the other `_..._PATH` constants:

```python
# custom_components/airport_software/client.py
_MYCODE_PATH = "/internal/mycode.aspx"
```

Add this method inside the `AirportSoftwareClient` class:

```python
    async def async_get_next_expiring_qualification(
        self, today: dt.date
    ) -> QualificationStatus | None:
        if self._auth_failed:
            raise InvalidAuth("airport-software previously rejected these credentials")
        if not self._authenticated:
            await self._async_login()

        page_html = await self._async_fetch(_MYCODE_PATH)
        if self._looks_like_login_page(page_html):
            await self._async_login()
            page_html = await self._async_fetch(_MYCODE_PATH)

        return parse_qualification_status(page_html, today)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_client.py -v -k qualification`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/client.py tests/test_client.py
git commit -m "feat: add next-expiring-qualification fetch"
```

---

## Task 15: Qualification status coordinator

**Files:**
- Modify: `custom_components/airport_software/coordinator.py`
- Test: `tests/test_coordinator.py` (append)

**Interfaces:**
- Consumes: `AirportSoftwareClient.async_get_next_expiring_qualification` (Task 14); `QualificationStatus` (Task 13); `DOMAIN`, `POLL_INTERVAL_SECONDS` (Task 1).
- Produces: `QualificationCoordinator(hass, entry, client)` subclassing `DataUpdateCoordinator[QualificationStatus | None]` — Task 16 (`__init__.py`) constructs this; Task 18 (`sensor.py`) reads `coordinator.data`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_coordinator.py (append)
from custom_components.airport_software.coordinator import QualificationCoordinator
from custom_components.airport_software.models import QualificationStatus


class _FakeQualificationClient:
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    async def async_get_next_expiring_qualification(self, today):
        if self._exc is not None:
            raise self._exc
        return self._result


async def test_qualification_update_data_returns_client_result(hass):
    qualification = QualificationStatus(
        label="Medical Class II",
        subcode="MEDICAL - CLASS II",
        end_date="2026-03-20",
        days_remaining=78,
        severity="ok",
    )
    client = _FakeQualificationClient(result=qualification)
    coordinator = QualificationCoordinator(hass, entry=None, client=client)

    assert await coordinator._async_update_data() == qualification


async def test_qualification_update_data_raises_config_entry_auth_failed_on_invalid_auth(hass):
    client = _FakeQualificationClient(exc=InvalidAuth("bad password"))
    coordinator = QualificationCoordinator(hass, entry=None, client=client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_qualification_update_data_raises_update_failed_on_network_error(hass):
    client = _FakeQualificationClient(exc=ConnectionError("boom"))
    coordinator = QualificationCoordinator(hass, entry=None, client=client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_coordinator.py -v -k qualification`
Expected: FAIL with `ImportError: cannot import name 'QualificationCoordinator'`

- [ ] **Step 3: Write the implementation**

Update the existing models import line near the top of `coordinator.py` (extended once already in Task 12) to also include `QualificationStatus`:

```python
# custom_components/airport_software/coordinator.py — change this existing line:
#   from .models import AircraftStatus, TowerDutyStatus
# to:
from .models import AircraftStatus, QualificationStatus, TowerDutyStatus
```

Append:

```python
# custom_components/airport_software/coordinator.py (append)
class QualificationCoordinator(DataUpdateCoordinator[QualificationStatus | None]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry | None,
        client: AirportSoftwareClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_qualification",
            update_interval=timedelta(seconds=POLL_INTERVAL_SECONDS),
        )
        self.config_entry = entry
        self._client = client

    async def _async_update_data(self) -> QualificationStatus | None:
        try:
            return await self._client.async_get_next_expiring_qualification(dt_util.now().date())
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(
                "airport-software rejected the configured credentials"
            ) from err
        except Exception as err:
            raise UpdateFailed(f"error communicating with airport-software: {err}") from err
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_coordinator.py -v -k qualification`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/coordinator.py tests/test_coordinator.py
git commit -m "feat: add QualificationCoordinator"
```

---

## Task 16: Integration setup (`__init__.py`)

**Files:**
- Create: `custom_components/airport_software/__init__.py`
- Test: `tests/test_init.py`

**Interfaces:**
- Consumes: `AirportSoftwareClient` (Task 7), `AirportSoftwareCoordinator` (Task 8), `DOMAIN`/`CONF_*` (Task 1), `TowerDutyCoordinator` (Task 12), `QualificationCoordinator` (Task 15).
- Produces: `async_setup_entry`, `async_unload_entry`; `hass.data[DOMAIN][entry.entry_id]` dict with keys `"coordinator"`, `"session"`, `"tower_duty_coordinator"`, and `"qualification_coordinator"` (the last two are `None` when their respective feature is disabled for that entry) — Tasks 17–18 (`binary_sensor.py`, `sensor.py`) read these in their `async_setup_entry`.

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_init.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.airport_software'` (no `__init__.py` yet)

- [ ] **Step 3: Write the implementation**

```python
# custom_components/airport_software/__init__.py
"""The airport-software integration."""
from __future__ import annotations

import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client import AirportSoftwareClient
from .const import (
    CONF_BASE_URL,
    CONF_ENABLE_FREE_REST_OF_DAY,
    CONF_ENABLE_QUALIFICATION_STATUS,
    CONF_ENABLE_TOWER_DUTY,
    CONF_FREE_REST_OF_DAY_CUTOFF,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)
from .coordinator import AirportSoftwareCoordinator, QualificationCoordinator, TowerDutyCoordinator

PLATFORMS = ["binary_sensor", "sensor"]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # A dedicated session (not HA's shared one) so this integration's
    # authenticated cookies never mix with other integrations' requests
    # to the same or other hosts. All coordinators below share this one
    # client/session — they're one login, not three.
    session = aiohttp.ClientSession()
    client = AirportSoftwareClient(
        session=session,
        base_url=entry.data[CONF_BASE_URL],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        enable_free_rest_of_day=entry.data[CONF_ENABLE_FREE_REST_OF_DAY],
        free_rest_of_day_cutoff=entry.data[CONF_FREE_REST_OF_DAY_CUTOFF],
    )
    coordinator = AirportSoftwareCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    # Both of these are optional, "fun" side features (not per-aircraft
    # data): a failure fetching them on startup shouldn't block the whole
    # integration (including aircraft data) from loading, so a transient
    # ConfigEntryNotReady here is logged and left to resolve on the next
    # normal poll rather than re-raised.
    tower_duty_coordinator: TowerDutyCoordinator | None = None
    if entry.data[CONF_ENABLE_TOWER_DUTY]:
        tower_duty_coordinator = TowerDutyCoordinator(hass, entry, client)
        try:
            await tower_duty_coordinator.async_config_entry_first_refresh()
        except ConfigEntryNotReady:
            _LOGGER.warning(
                "Could not fetch tower duty data during setup; will retry on next poll"
            )

    qualification_coordinator: QualificationCoordinator | None = None
    if entry.data[CONF_ENABLE_QUALIFICATION_STATUS]:
        qualification_coordinator = QualificationCoordinator(hass, entry, client)
        try:
            await qualification_coordinator.async_config_entry_first_refresh()
        except ConfigEntryNotReady:
            _LOGGER.warning(
                "Could not fetch qualification status during setup; will retry on next poll"
            )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "session": session,
        "tower_duty_coordinator": tower_duty_coordinator,
        "qualification_coordinator": qualification_coordinator,
    }

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
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/__init__.py tests/test_init.py
git commit -m "feat: wire up integration setup/unload with dedicated session and optional coordinators"
```

---

## Task 17: Binary sensor platform

**Files:**
- Create: `custom_components/airport_software/binary_sensor.py`
- Test: `tests/test_binary_sensor.py`

**Interfaces:**
- Consumes: `AirportSoftwareCoordinator` (Task 8), `hass.data[DOMAIN][entry.entry_id]["coordinator"]` (Task 16), `CONF_ENABLE_FREE_REST_OF_DAY` (Task 1).
- Produces: nothing consumed by later tasks (leaf platform).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_binary_sensor.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_binary_sensor.py -v`
Expected: FAIL — all three states are `None`/missing (no `binary_sensor.py` platform registered yet)

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

from .const import CONF_ENABLE_FREE_REST_OF_DAY, DOMAIN
from .coordinator import AirportSoftwareCoordinator


def _device_info(tail_number: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, tail_number)},
        name=tail_number,
        manufacturer="airport-software DS GmbH",
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AirportSoftwareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[BinarySensorEntity] = [
        AirportSoftwareInUseBinarySensor(coordinator, tail_number)
        for tail_number in coordinator.data
    ]
    if entry.data[CONF_ENABLE_FREE_REST_OF_DAY]:
        entities.extend(
            AirportSoftwareFreeRestOfDayBinarySensor(coordinator, tail_number)
            for tail_number in coordinator.data
        )
    async_add_entities(entities)


class AirportSoftwareInUseBinarySensor(
    CoordinatorEntity[AirportSoftwareCoordinator], BinarySensorEntity
):
    _attr_has_entity_name = True
    _attr_translation_key = "in_use"

    def __init__(self, coordinator: AirportSoftwareCoordinator, tail_number: str) -> None:
        super().__init__(coordinator)
        self._tail_number = tail_number
        self._attr_unique_id = f"{tail_number}_in_use"
        self._attr_device_info = _device_info(tail_number)

    @property
    def is_on(self) -> bool | None:
        status = self.coordinator.data.get(self._tail_number)
        return status.in_use if status else None


class AirportSoftwareFreeRestOfDayBinarySensor(
    CoordinatorEntity[AirportSoftwareCoordinator], BinarySensorEntity
):
    _attr_has_entity_name = True
    _attr_translation_key = "free_rest_of_day"

    def __init__(self, coordinator: AirportSoftwareCoordinator, tail_number: str) -> None:
        super().__init__(coordinator)
        self._tail_number = tail_number
        self._attr_unique_id = f"{tail_number}_free_rest_of_day"
        self._attr_device_info = _device_info(tail_number)

    @property
    def is_on(self) -> bool | None:
        status = self.coordinator.data.get(self._tail_number)
        return status.free_rest_of_day if status else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        status = self.coordinator.data.get(self._tail_number)
        if not status:
            return {}
        return {"available_from": status.available_from_today}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_binary_sensor.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/binary_sensor.py tests/test_binary_sensor.py
git commit -m "feat: add in_use and optional free_rest_of_day binary sensors"
```

---

## Task 18: Sensor platform

**Files:**
- Create: `custom_components/airport_software/sensor.py`
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes: `AirportSoftwareCoordinator` (Task 8), `TowerDutyCoordinator` (Task 12), `QualificationCoordinator` (Task 15), `hass.data[DOMAIN][entry.entry_id]` keys `"coordinator"`, `"tower_duty_coordinator"`, `"qualification_coordinator"` (Task 16), `CONF_ENABLE_TOWER_DUTY`/`CONF_ENABLE_QUALIFICATION_STATUS` (Task 1).
- Produces: nothing consumed by later tasks (leaf platform).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sensor.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sensor.py -v`
Expected: FAIL — all states are `None` (no `sensor.py` platform registered yet)

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

from .const import CONF_ENABLE_QUALIFICATION_STATUS, CONF_ENABLE_TOWER_DUTY, DOMAIN
from .coordinator import AirportSoftwareCoordinator, QualificationCoordinator, TowerDutyCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: AirportSoftwareCoordinator = entry_data["coordinator"]

    entities: list[SensorEntity] = []
    for tail_number in coordinator.data:
        entities.append(AirportSoftwareConditionSensor(coordinator, tail_number))
        entities.append(AirportSoftwareRemainingHoursSensor(coordinator, tail_number))

    if entry.data[CONF_ENABLE_TOWER_DUTY]:
        entities.append(TowerDutyNowSensor(entry_data["tower_duty_coordinator"], entry.entry_id))

    if entry.data[CONF_ENABLE_QUALIFICATION_STATUS]:
        entities.append(
            NextExpiringQualificationSensor(
                entry_data["qualification_coordinator"], entry.entry_id
            )
        )

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


class TowerDutyNowSensor(CoordinatorEntity[TowerDutyCoordinator], SensorEntity):
    """Who's currently on Flugleitung (tower) duty. Club-wide, not per-aircraft."""

    _attr_has_entity_name = True
    _attr_translation_key = "tower_duty_now"

    def __init__(self, coordinator: TowerDutyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_tower_duty_now"

    @property
    def native_value(self) -> str | None:
        duty = self.coordinator.data
        if duty is None:
            return None
        return duty.on_duty if duty.on_duty else "none"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        duty = self.coordinator.data
        return {"note": duty.note} if duty else {}


class NextExpiringQualificationSensor(
    CoordinatorEntity[QualificationCoordinator], SensorEntity
):
    """Days remaining until the soonest-expiring license/qualification item."""

    _attr_has_entity_name = True
    _attr_translation_key = "next_expiring_qualification"
    _attr_native_unit_of_measurement = "d"

    def __init__(self, coordinator: QualificationCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_next_expiring_qualification"

    @property
    def native_value(self) -> int | None:
        qualification = self.coordinator.data
        return qualification.days_remaining if qualification else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        qualification = self.coordinator.data
        if not qualification:
            return {}
        return {
            "label": qualification.label,
            "subcode": qualification.subcode,
            "end_date": qualification.end_date,
            "severity": qualification.severity,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sensor.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add custom_components/airport_software/sensor.py tests/test_sensor.py
git commit -m "feat: add per-aircraft sensors plus optional tower duty and qualification sensors"
```

---

## Task 19: Full test suite and README

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing (final documentation/polish task).

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: all tests pass (Tasks 2–18's tests, ~60 tests total)

- [ ] **Step 2: Write `README.md`**

```markdown
# airport-software Home Assistant Integration

Reports aircraft status from an [airport-software](https://www.airport-software.com)
reservation system instance into Home Assistant.

## What you get

Per aircraft (one HA device per tail number), always:

- `binary_sensor.<tail>_in_use` — on when the aircraft's key is checked out
- `sensor.<tail>_condition` — `ready` or `maintenance`, with `open_info_count`
  and `remarks` attributes
- `sensor.<tail>_remaining_hours` — hours remaining to the next inspection
  (can be negative if overdue)

Optionally (each on by default, toggle off during setup if you don't want
them):

- `binary_sensor.<tail>_free_rest_of_day` — on only if the aircraft has no
  further booking today AND becomes available at or before your configured
  cutoff time (default 18:00). The actual available-from time (e.g.
  "immediate" or an `HH:MM` time) is always available as the
  `available_from` attribute, even when the boolean is off because it's
  past the cutoff.
- `sensor.tower_duty_now` — who's currently on Flugleitung (tower) duty,
  club-wide (not per-aircraft), resolved from the tower duty calendar.
  State is the on-duty name(s), `"none"` if today's schedule has a gap
  right now, or `unavailable` if today's date couldn't even be found on the
  fetched calendar page. A `note` attribute carries any partial-coverage
  caveat shown on the site (e.g. "until 14:00").
- `sensor.next_expiring_qualification` — days remaining until your
  soonest-expiring license/qualification/medical item (negative if already
  past due). A `severity` attribute is `ok` (>30 days or never expires),
  `info` (≤30 days), `warning` (≤14 days), or `issue` (past due), with
  `label`, `subcode`, and `end_date` attributes for the specific item.

Polled every 15 minutes. The tower-duty and qualification-status fetches
share the same login session as the aircraft data — enabling them doesn't
mean logging in more often, just fetching one or two extra pages per poll.

## Installation

Via HACS: add this repository as a custom repository, install
"airport-software", restart Home Assistant, then add the integration via
Settings → Devices & Services and enter your club's base URL, member
number, and password. Optionally adjust or disable the "free for the rest
of the day" cutoff, tower duty, and qualification status features during
setup.

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
   you see on the site's own booking overview and "Heute verfügbar" pages.
3. If enabled, confirm `sensor.tower_duty_now` matches the Flugleitung
   calendar and `sensor.next_expiring_qualification` matches your own
   "Berechtigungsstatus" page.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```
