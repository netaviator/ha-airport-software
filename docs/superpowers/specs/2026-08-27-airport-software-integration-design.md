# Home Assistant Integration for airport-software — Design

## Purpose

Report the status of club aircraft (from the "airport-software" reservation
system's booking overview page) into Home Assistant, as one entity set per
aircraft, on a periodic poll.

## Background

"airport-software" (airport-software.com) is a commercial reservation/booking
platform used by multiple German flying clubs, running on ASP.NET WebForms
behind Cloudflare. The reference instance for development is
`https://fly-mainz.de`. Investigation during design confirmed:

- Login is classic ASP.NET WebForms Forms Authentication: `GET
  /login/login.aspx` returns a page with `__VIEWSTATE`,
  `__VIEWSTATEGENERATOR`, and `__EVENTVALIDATION` hidden fields. The login
  button (`ctl00$MainContentPlaceHolder$cmdLogin`) is wired to
  `__doPostBack()`, which calls `form.submit()` directly — per the HTML
  submission spec, a script-invoked `form.submit()` never includes the
  activated submit button's name/value pair. The correct POST must therefore
  set `__EVENTTARGET=ctl00$MainContentPlaceHolder$cmdLogin` and
  `__EVENTARGUMENT=` (empty), and must **omit** the `cmdLogin` field entirely.
  Sending `cmdLogin` and leaving `__EVENTTARGET` empty causes the server to
  silently treat the request as a fresh (non-postback) page load — no error,
  just a regenerated page.
- A believable-but-plausible failure mode during scraping-mechanism
  development is bad credentials, not a broken mechanism: the app returns a
  precise error (`"Das Passwort für den Benutzer <NAME> ist ungültig! Noch N
  Versuche verbleiben."` — "invalid password, N attempts remaining") with a
  visibly decrementing attempt counter. **This confirms the target account
  can be locked out by repeated bad attempts** — a hard constraint on how the
  integration (and its tests) must behave.
- On success, the login POST redirects (302) to the originally-requested
  page, and a `BookingSysAuth` cookie is issued alongside the existing
  `ASP.NET_SessionId`.
- The status data lives in `/internal/booking_overview.aspx`, in a table
  (`#ctl00_MainContentPlaceHolder_divZustand`) with one row per aircraft:
  tail number, a key-icon (checked out vs. available), a condition cell
  ("Klar", optionally "Klar (N Infos)" linking to a defects page, or
  "Wartung" for maintenance), remaining hours to next inspection (`HH:MM`,
  can be negative/overdue), and a free-text remarks cell.

## Scope

In scope: reporting per-aircraft status (availability, condition, remaining
hours, remarks) as Home Assistant entities, polled periodically. Out of
scope: reservations/bookings themselves, creating/editing bookings, any
other page of the reservation system.

## Architecture

A standard HACS-installable custom integration at
`custom_components/airport_software/`, built generically (configurable base
URL + credentials) so it can serve any club running airport-software, not
just fly-mainz.de.

```
custom_components/airport_software/
  manifest.json       # integration metadata, HACS-compatible
  const.py            # domain, defaults (poll interval, etc.)
  models.py           # AircraftStatus (frozen dataclass)
  client.py           # HTTP client: login, session mgmt, HTML parsing
  coordinator.py       # DataUpdateCoordinator, polls client.py
  config_flow.py       # setup UI + reauth flow
  sensor.py             # condition + remaining_hours sensors
  binary_sensor.py      # in_use binary sensor
```

Each aircraft (tail number) is registered as one HA device, grouping its
entities.

## Components

### `models.py`

```python
@dataclass(frozen=True)
class AircraftStatus:
    tail_number: str
    in_use: bool
    condition: Literal["ready", "maintenance"]
    open_info_count: int
    remaining_hours: float  # can be negative (overdue)
    remarks: str
```

### `client.py`

Responsible for:

- **Login**: replicate the validated postback sequence exactly (see
  Background). Use a realistic header set (`Referer`, `Origin`, `Accept`,
  `Cache-Control`, `Sec-Fetch-*`) even though the minimal required subset
  wasn't fully isolated during investigation — over-providing is cheap
  insurance against re-triggering a multi-hour debugging cycle if
  Cloudflare's bot heuristics are sensitive to their absence.
- **Credential-failure detection**: parse the login response for the
  "invalid password"/attempts-remaining message (or, more robustly, detect
  that the response re-rendered the login page with a populated
  `#ctl00_fehlertext` error block). On detecting this, raise a distinct
  `InvalidAuth` exception — this must never trigger an automatic retry.
- **Session reuse**: keep the authenticated `aiohttp`/session across polls;
  only re-run the login sequence when a fetch of `booking_overview.aspx`
  redirects back to the login page (session expired).
- **Parsing**: parse `#ctl00_MainContentPlaceHolder_divZustand` into a list
  of `AircraftStatus`. Use `html.parser`/regex consistent with the
  investigation scripts — no new heavy dependency (e.g. no
  BeautifulSoup) unless parsing complexity grows enough to justify one.

### `coordinator.py`

A `DataUpdateCoordinator` subclass, default 15 minute interval (configurable
later if needed, not required for v1). On `InvalidAuth` from the client,
raises `ConfigEntryAuthFailed` — this stops the coordinator's automatic
polling entirely and puts the config entry into HA's reauth-required state.
**No automatic retry of a failed login ever happens** — the account lockout
risk observed during development is a hard requirement here, not a nice-to-have.

On network errors or parse errors (site structure changed), raises
`UpdateFailed` — entities go `unavailable`, normal polling resumes next
interval, no risk to the account.

### `config_flow.py`

Standard `ConfigFlow`: base URL, member number, password. Validates by
attempting one real login during setup (the only place a "test this
actually works" login attempt happens interactively, with the user directly
in the loop to notice and stop on a lockout warning). Implements
`async_step_reauth` for when `ConfigEntryAuthFailed` fires later.

### `sensor.py` / `binary_sensor.py`

Per aircraft:

- `binary_sensor.<tail>_in_use` — on = checked out, off = available.
- `sensor.<tail>_condition` — state `ready`/`maintenance`, attributes
  `open_info_count`, `remarks`.
- `sensor.<tail>_remaining_hours` — numeric (hours), can be negative.

## Testing

Per TDD: write tests first for the two pure-logic units (field extraction +
HTML table parsing) before their implementations.

- **Login field-extraction** and **status-table parsing** are tested against
  **saved HTML fixtures** (captured during this design's investigation —
  sanitized of the real session/viewstate/credential values) — never against
  the live site in automated tests.
- **No CI or automated test ever performs a live login** against
  fly-mainz.de or any other real instance, given the demonstrated lockout
  risk. Live-login verification is a one-time, human-driven manual step
  (documented in the plan/README), not a repeatable test.
- Coordinator/config-flow tests use a fake client (mock), not the real HTTP
  layer.

## Out of scope / explicit non-goals

- No headless-browser fallback: the plain-HTTP mechanism is proven to work
  end-to-end; there's no need for the Playwright/Docker-add-on architecture
  discussed and rejected earlier in design.
- No booking/reservation management (read-only status reporting only).
- No caching of credentials outside HA's own config-entry storage (HA
  encrypts config entry data at rest; no separate secrets file).
