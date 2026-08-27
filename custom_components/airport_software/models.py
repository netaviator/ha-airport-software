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
