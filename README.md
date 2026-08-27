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
