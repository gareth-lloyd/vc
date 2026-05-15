"""Availability queries backed by live holds and non-terminal bookings.

A property date range is unavailable if it overlaps either:

- a non-terminal `reservations.Booking`
  (`status NOT IN reservations.enums.TERMINAL_BOOKING_STATUSES`), or
- a *live* `reservations.BookingHold` (`released_at IS NULL` and
  `expires_at > now`).

Bookings are queried directly — `BookingService.create_from_quotation_line`
releases the quotation hold and does *not* place a booking-scoped hold, so
a confirmed booking has no covering hold row.

The reservations models are imported lazily inside each method to avoid an
app-load cycle (the views layer follows the same convention).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from reservations.enums import TERMINAL_BOOKING_STATUSES, BookingHoldReason

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


# Most-significant reason wins when several overlap one day.
_REASON_PRIORITY = {"booked": 3, "owner_block": 2, "maintenance": 1, "hold": 0}

_HOLD_REASON_KIND = {
    BookingHoldReason.OWNER_BLOCK.value: "owner_block",
    BookingHoldReason.MAINTENANCE.value: "maintenance",
}


def _hold_kind(reason: str) -> str:
    return _HOLD_REASON_KIND.get(reason, "hold")


class AvailabilityService:
    """Read availability off `BookingHold` + `Booking` overlap queries."""

    @classmethod
    def _live_holds(
        cls,
        property: Any,
        date_from: date,
        date_to: date,
        *,
        ignore_hold_ids: Iterable[int] | None = None,
    ) -> Any:
        from reservations.models.booking import BookingHold

        return BookingHold.live_overlapping(
            property=property,
            date_from=date_from,
            date_to=date_to,
            exclude_ids=list(ignore_hold_ids) if ignore_hold_ids else None,
        )

    @classmethod
    def _active_bookings(cls, property: Any, date_from: date, date_to: date) -> Any:
        from reservations.models.booking import Booking

        return Booking.objects.filter(
            property=property,
            date_from__lt=date_to,
            date_to__gt=date_from,
        ).exclude(status__in=TERMINAL_BOOKING_STATUSES)

    @classmethod
    def is_available(
        cls,
        property: Any,
        date_from: date,
        date_to: date,
        *,
        ignore_hold_ids: Iterable[int] | None = None,
    ) -> bool:
        if cls._active_bookings(property, date_from, date_to).exists():
            return False
        return not cls._live_holds(
            property,
            date_from,
            date_to,
            ignore_hold_ids=ignore_hold_ids,
        ).exists()

    @classmethod
    def conflicts(
        cls,
        property: Any,
        date_from: date,
        date_to: date,
    ) -> list[Conflict]:
        result: list[Conflict] = []
        for booking in cls._active_bookings(property, date_from, date_to):
            result.append(
                Conflict(
                    kind="booked",
                    date_from=booking.date_from,
                    date_to=booking.date_to,
                    detail=f"Booking {booking.reference}",
                )
            )
        for hold in cls._live_holds(property, date_from, date_to):
            result.append(
                Conflict(
                    kind=_hold_kind(hold.reason),
                    date_from=hold.date_from,
                    date_to=hold.date_to,
                    detail=hold.get_reason_display(),
                )
            )
        return result

    @classmethod
    def calendar(
        cls,
        property: Any,
        range_start: date,
        range_end: date,
    ) -> dict[date, CellStatus]:
        end_exclusive = range_end + timedelta(days=1)
        bookings = list(cls._active_bookings(property, range_start, end_exclusive))
        holds = list(cls._live_holds(property, range_start, end_exclusive))

        result: dict[date, CellStatus] = {}
        cursor = range_start
        while cursor <= range_end:
            result[cursor] = CellStatus(available=True)
            cursor += timedelta(days=1)

        def _mark(start: date, end: date, reason: str) -> None:
            day = max(start, range_start)
            stop = min(end - timedelta(days=1), range_end)
            while day <= stop:
                cell = result[day]
                if cell.available or _REASON_PRIORITY[reason] > _REASON_PRIORITY.get(
                    cell.reason, -1
                ):
                    result[day] = CellStatus(available=False, reason=reason)
                day += timedelta(days=1)

        for hold in holds:
            _mark(hold.date_from, hold.date_to, _hold_kind(hold.reason))
        for booking in bookings:
            _mark(booking.date_from, booking.date_to, "booked")

        return result
