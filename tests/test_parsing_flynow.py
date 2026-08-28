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


def test_parse_flynow_table_gap_between_slots_is_not_free_rest_of_day():
    """An aircraft with two slots today (available now until 14:00, then
    booked, then available again from 17:00 until end of day) has a gap in
    the middle — it isn't free for the *rest* of the day even though its
    last slot runs to end of day."""
    html = load_fixture("booking_flynow.html")
    result = parse_flynow_table(html, cutoff="18:00")
    assert result["D-ELHW"] == ("immediate", False)
