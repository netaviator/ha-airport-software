"""Tests for HTML parsing of ASP.NET login pages."""
from tests.conftest import load_fixture
from custom_components.airport_software.parsing import extract_hidden_fields, login_failed


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


def test_login_failed_true_on_error_page():
    html = load_fixture("login_response_invalid.html")
    assert login_failed(html) is True


def test_login_failed_false_on_success_page():
    html = load_fixture("login_response_success.html")
    assert login_failed(html) is False
