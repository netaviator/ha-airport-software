"""Tests for HTML parsing of aircraft status overview page."""
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
