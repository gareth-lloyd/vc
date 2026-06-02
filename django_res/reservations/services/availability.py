"""Availability queries backed by live holds and blocking bookings.

A property date range is unavailable if it overlaps either:

- a *blocking* `reservations.Booking`
  (`Booking.objects.overlapping_blocking(...)` — `status IN
  reservations.enums.OVERLAP_BLOCKING_BOOKING_STATUSES`), or
- a *live* `reservations.BookingHold`
  (`BookingHold.live_overlapping(...)` — `released_at IS NULL` and
  `expires_at > now`).

Both predicates are the canonical model-layer ones, shared verbatim with the
catalogue-search filter (`properties.filters.property`), so the calendar and
search can never drift on which bookings/holds occupy a range.

Bookings are queried directly — `BookingService.create_from_quotation_line`
releases the quotation hold and does *not* place a booking-scoped hold, so
a confirmed booking has no covering hold row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

from reservations.enums import OPERATOR_EDITABLE_HOLD_REASONS, BookingHoldReason
from reservations.models.booking import Booking, BookingHold

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
    """Per-day cell on the admin availability grid.

    ``block_id`` is the originating ``BookingHold`` pk, but only for the
    operator-editable reasons (owner_block / maintenance / manual). It is
    ``None`` for bookings and for system holds (quotation / booking deposit)
    so the UI never offers an edit affordance on read-only state.

    ``segments`` is present only on a true changeover day (one stay departs
    the morning, another arrives the afternoon) — see ``_changeover_segments``.
    """

    available: bool
    reason: str = ""
    block_id: int | None = None
    segments: dict[str, CellStatus] | None = None


# Most-significant reason wins when several overlap one day.
_REASON_PRIORITY = {
    "booked": 6,
    "owner_block": 5,
    "maintenance": 4,
    "manual": 3,
    "booking_deposit": 2,
    "quotation": 1,
}

_HOLD_REASON_KIND = {
    BookingHoldReason.QUOTATION_OPEN.value: "quotation",
    BookingHoldReason.BOOKING_DEPOSIT_PENDING.value: "booking_deposit",
    BookingHoldReason.OWNER_BLOCK.value: "owner_block",
    BookingHoldReason.MAINTENANCE.value: "maintenance",
    BookingHoldReason.MANUAL.value: "manual",
}

# Editable hold reasons map 1:1 onto their cell "kind", so the operator-editable
# kinds are exactly the editable reasons.
_EDITABLE_KINDS = frozenset(OPERATOR_EDITABLE_HOLD_REASONS)


def _hold_kind(reason: str) -> str:
    return _HOLD_REASON_KIND.get(reason, "quotation")


def _resolve_changeover_times(property: Any) -> tuple[time | None, time | None]:
    """Effective (property→group) check-out / check-in times, or (None, None).

    A property with no settings, or whose group has no settings, simply has
    no half-day boundary — the day stays whole. Never raises.
    """
    try:
        settings = property.settings
    except ObjectDoesNotExist:
        return None, None
    try:
        return (
            settings.effective("check_out_time"),
            settings.effective("check_in_time"),
        )
    except (ObjectDoesNotExist, AttributeError):
        return None, None


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
        return BookingHold.live_overlapping(
            property=property,
            date_from=date_from,
            date_to=date_to,
            exclude_ids=list(ignore_hold_ids) if ignore_hold_ids else None,
        )

    @classmethod
    def _active_bookings(cls, property: Any, date_from: date, date_to: date) -> Any:
        return Booking.objects.overlapping_blocking(
            property=property,
            date_from=date_from,
            date_to=date_to,
        )

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

        def _mark(start: date, end: date, reason: str, block_id: int | None) -> None:
            day = max(start, range_start)
            stop = min(end - timedelta(days=1), range_end)
            while day <= stop:
                cell = result[day]
                if cell.available or _REASON_PRIORITY[reason] > _REASON_PRIORITY.get(
                    cell.reason, -1
                ):
                    result[day] = CellStatus(available=False, reason=reason, block_id=block_id)
                day += timedelta(days=1)

        for hold in holds:
            kind = _hold_kind(hold.reason)
            _mark(
                hold.date_from,
                hold.date_to,
                kind,
                hold.pk if kind in _EDITABLE_KINDS else None,
            )
        for booking in bookings:
            _mark(booking.date_from, booking.date_to, "booked", None)

        cls._apply_changeover_segments(property, holds, bookings, result, range_start, range_end)
        return result

    @classmethod
    def _apply_changeover_segments(
        cls,
        property: Any,
        holds: list[Any],
        bookings: list[Any],
        result: dict[date, CellStatus],
        range_start: date,
        range_end: date,
    ) -> None:
        """Split a true changeover day (one stay departs AM, another arrives PM).

        A date is a changeover iff some interval's exclusive checkout (`date_to`)
        coincides with another interval's check-in (`date_from`). Reuses the
        already-fetched holds/bookings — no extra availability queries.
        """
        starts: dict[date, list[CellStatus]] = {}
        ends: dict[date, list[CellStatus]] = {}

        def _add(d_from: date, d_to: date, st: CellStatus) -> None:
            starts.setdefault(d_from, []).append(st)
            ends.setdefault(d_to, []).append(st)

        for hold in holds:
            kind = _hold_kind(hold.reason)
            _add(
                hold.date_from,
                hold.date_to,
                CellStatus(
                    available=False,
                    reason=kind,
                    block_id=hold.pk if kind in _EDITABLE_KINDS else None,
                ),
            )
        for booking in bookings:
            _add(
                booking.date_from,
                booking.date_to,
                CellStatus(available=False, reason="booked"),
            )

        candidates = [d for d in starts if d in ends and range_start <= d <= range_end]
        if not candidates:
            return

        check_out, check_in = _resolve_changeover_times(property)
        if check_out is None or check_in is None or check_out > check_in:
            return

        def _pick(cands: list[CellStatus]) -> CellStatus:
            return max(cands, key=lambda c: _REASON_PRIORITY.get(c.reason, -1))

        for day in candidates:
            am = _pick(ends[day])
            pm = _pick(starts[day])
            rollup = _pick([am, pm])
            result[day] = CellStatus(
                available=False,
                reason=rollup.reason,
                block_id=rollup.block_id,
                segments={"am": am, "pm": pm},
            )
