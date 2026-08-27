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
