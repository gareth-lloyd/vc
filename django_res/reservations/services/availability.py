"""Availability queries backed by live holds and occupying bookings.

A property date range is unavailable if it overlaps either:

- an *occupying* `reservations.Booking`
  (`Booking.objects.occupying(...)` — any booking not in
  `reservations.enums.TERMINAL_BOOKING_STATUSES`, so resting legacy DRAFT
  imports count), or
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

    ``quotation_id`` is the owning quotation of a quotation hold — a read-only
    click-through to the quotation page, deliberately separate from
    ``block_id`` so linking never doubles as an edit affordance.

    ``segments`` carries an AM/PM split, set by ``_apply_changeover_segments``
    on two kinds of day: a *true changeover* (one stay departs the morning,
    another arrives the afternoon — both halves occupied, ``available=False``)
    and a *lone booking checkout* (AM booked, PM free — the cell stays
    ``available=True`` because the afternoon is sellable as a new arrival).
    """

    available: bool
    reason: str = ""
    block_id: int | None = None
    quotation_id: int | None = None
    segments: dict[str, CellStatus] | None = None


# Most-significant reason wins when several overlap one day.
_REASON_PRIORITY = {
    "booked": 6,
    "owner_block": 5,
    "maintenance": 4,
    "manual": 3,
    "quotation": 1,
}

_HOLD_REASON_KIND = {
    BookingHoldReason.QUOTATION_OPEN.value: "quotation",
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
    """The property's check-out / check-in times, or (None, None).

    A property with no settings row, or with the times unset, simply has no
    half-day boundary — the day stays whole. Never raises.
    """
    try:
        settings = property.settings
    except ObjectDoesNotExist:
        return None, None
    return settings.check_out_time, settings.check_in_time


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
        return Booking.objects.occupying(
            property=property,
            date_from=date_from,
            date_to=date_to,
        )

    @classmethod
    def multi(
        cls,
        property_ids: Iterable[int],
        date_from: date,
        date_to: date,
    ) -> tuple[Any, Any]:
        """Range bands for the multi-villa timeline: `(holds_qs, bookings_qs)`.

        Returns the raw overlapping intervals (not per-day cells) across the
        requested properties, via the canonical predicates. Holds linked to a
        booking are excluded as a guard: a stay must paint one band, and the
        occupying Booking row is the canonical one. (No production path
        currently creates booking-linked holds, but the schema allows them.)
        """
        ids = list(property_ids)
        holds = BookingHold.live_overlapping(
            date_from=date_from,
            date_to=date_to,
        ).filter(property_id__in=ids, booking_id__isnull=True)
        bookings = (
            Booking.objects.occupying(date_from=date_from, date_to=date_to)
            .filter(property_id__in=ids)
            # GAP-045 Unit 3d-3: band labels resolve guest name solely from the
            # Person mirror; name only, so the join suffices (no email prefetch).
            .select_related("person")
        )
        return holds, bookings

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

        def _mark(
            start: date,
            end: date,
            reason: str,
            block_id: int | None,
            quotation_id: int | None = None,
        ) -> None:
            day = max(start, range_start)
            stop = min(end - timedelta(days=1), range_end)
            while day <= stop:
                cell = result[day]
                if cell.available or _REASON_PRIORITY[reason] > _REASON_PRIORITY.get(
                    cell.reason, -1
                ):
                    result[day] = CellStatus(
                        available=False,
                        reason=reason,
                        block_id=block_id,
                        quotation_id=quotation_id,
                    )
                day += timedelta(days=1)

        for hold in holds:
            kind = _hold_kind(hold.reason)
            _mark(
                hold.date_from,
                hold.date_to,
                kind,
                hold.pk if kind in _EDITABLE_KINDS else None,
                hold.quotation_id if kind == "quotation" else None,
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
        """Split changeover / turnover days into AM (departing) + PM (arriving) halves.

        Two cases, both gated on the property allowing same-day changeover
        (effective check-out earlier than check-in):

        1. **True changeover** — some interval's exclusive checkout (`date_to`)
           coincides with another interval's check-in (`date_from`). Both halves
           are occupied; the day stays unavailable. Works for any reason mix.
        2. **Lone booking checkout** — a *booking's* `date_to` with no arriving
           stay that day. The departing guest holds the morning, but the
           afternoon is sellable as a new arrival, so the day stays
           **available** with an AM `booked` / PM available split. Bookings only:
           an owner/maintenance/manual block has no checkout to turn over, so all
           blocks remain whole-day.

        Reuses the already-fetched holds/bookings — the only extra query is the
        one-off changeover-time resolution, and only when there is a boundary to
        split.
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
                    quotation_id=hold.quotation_id if kind == "quotation" else None,
                ),
            )
        for booking in bookings:
            _add(
                booking.date_from,
                booking.date_to,
                CellStatus(available=False, reason="booked"),
            )

        candidates = [d for d in starts if d in ends and range_start <= d <= range_end]
        # Lone booking checkouts: a booking departs but nothing arrives, and the
        # checkout day isn't otherwise occupied. (`date_to` is exclusive, so the
        # cell is normally available unless another interval covers it.)
        lone_checkouts: dict[date, CellStatus] = {}
        for booking in bookings:
            day = booking.date_to
            if day in candidates or not (range_start <= day <= range_end):
                continue
            if not result[day].available:
                continue
            lone_checkouts[day] = CellStatus(available=False, reason="booked")

        if not candidates and not lone_checkouts:
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
                quotation_id=rollup.quotation_id,
                segments={"am": am, "pm": pm},
            )

        for day, am in lone_checkouts.items():
            # Sellable as a new arrival: available, AM booked / PM free.
            result[day] = CellStatus(
                available=True,
                reason="",
                segments={"am": am, "pm": CellStatus(available=True)},
            )
