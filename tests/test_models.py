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
