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
