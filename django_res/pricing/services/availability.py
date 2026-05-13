from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass
class Conflict:
    """A reason why a date range is not bookable."""

    kind: str
    date_from: date
    date_to: date
    detail: str = ""


@dataclass
class CellStatus:
    """Per-day cell on the admin availability grid."""

    available: bool
    reason: str = ""


class AvailabilityService:
    """Availability queries — full implementation depends on `reservations.Booking`.

    Lives here (not `reservations`) because the engine consults change-over
    rules at quote time. For now `is_available` returns True and `conflicts`
    returns []; once `reservations.Booking` and `reservations.BookingHold`
    exist, those models' EXCLUDE constraints provide the real backing query.
    """

    @classmethod
    def is_available(
        cls,
        property: Any,
        date_from: date,
        date_to: date,
        *,
        ignore_hold_ids: Iterable[int] | None = None,
    ) -> bool:
        return True

    @classmethod
    def conflicts(
        cls,
        property: Any,
        date_from: date,
        date_to: date,
    ) -> list[Conflict]:
        return []

    @classmethod
    def calendar(
        cls,
        property: Any,
        range_start: date,
        range_end: date,
    ) -> dict[date, CellStatus]:
        result: dict[date, CellStatus] = {}
        cursor = range_start
        while cursor <= range_end:
            result[cursor] = CellStatus(available=True)
            cursor += timedelta(days=1)
        return result
