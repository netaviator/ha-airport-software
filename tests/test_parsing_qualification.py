import datetime as dt

from tests.conftest import load_fixture
from custom_components.airport_software.models import QualificationStatus
from custom_components.airport_software.parsing import parse_qualification_status


def test_parse_qualification_status_ok_when_far_from_expiry():
    # mycode.html has two real (non-9999) candidates: "Nachtflug" (ends
    # 08.03.2026) and "Medical Class II" (ends 20.03.2026). Nachtflug's
    # end date is earlier, so min() always picks it over Medical Class II
    # regardless of `today` -- see
    # test_parse_qualification_status_prefers_earlier_date_even_when_past_due
    # below for the case where this matters (an expired item beating a
    # future one).
    html = load_fixture("mycode.html")
    result = parse_qualification_status(html, today=dt.date(2026, 1, 1))
    assert result.label == "Nachtflug"
    assert result.days_remaining == 66
    assert result.severity == "ok"


def test_parse_qualification_status_info_within_30_days():
    html = load_fixture("mycode.html")
    result = parse_qualification_status(html, today=dt.date(2026, 2, 20))
    assert result.days_remaining == 16
    assert result.severity == "info"


def test_parse_qualification_status_warning_within_14_days():
    html = load_fixture("mycode.html")
    result = parse_qualification_status(html, today=dt.date(2026, 3, 6))
    assert result.days_remaining == 2
    assert result.severity == "warning"


def test_parse_qualification_status_issue_when_past_due():
    html = load_fixture("mycode.html")
    result = parse_qualification_status(html, today=dt.date(2026, 3, 25))
    assert result.days_remaining == -17
    assert result.severity == "issue"


def test_parse_qualification_status_prefers_earlier_date_even_when_past_due():
    """min() must pick the numerically-earliest end date across two real
    candidates, even when that means preferring an already-expired item
    ("Nachtflug", ends 08.03.2026, i.e. 7 days past due at this `today`)
    over an item that hasn't expired yet ("Medical Class II", ends
    20.03.2026, i.e. 5 days in the future at this `today`).
    """
    html = load_fixture("mycode.html")
    result = parse_qualification_status(html, today=dt.date(2026, 3, 15))
    assert result.label == "Nachtflug"
    assert result.days_remaining == -7
    assert result.severity == "issue"


def test_parse_qualification_status_ignores_never_expiring_entries():
    html = load_fixture("mycode_never_expires_only.html")
    result = parse_qualification_status(html, today=dt.date(2026, 1, 1))
    assert result == QualificationStatus(
        label=None, subcode=None, end_date=None, days_remaining=None, severity="ok"
    )


def test_parse_qualification_status_returns_none_when_table_missing():
    assert parse_qualification_status("<html></html>", today=dt.date(2026, 1, 1)) is None
