"""ConciergeService — concierge-line orchestration.

Owns the `Booking.adjustment` denorm recompute (`recompute_adjustment`):
the signal receivers on `BookingConciergeItem` save/delete call it, and so
must any **bulk** mutation of concierge rows (`queryset.update()`,
`bulk_create`, `bulk_update`), which fire no signals and otherwise leave the
denorm stale — the same bulk-write/signal blind spot documented for AuditLog
in `django_res/CLAUDE.md` (FG-011, sibling of FG-016).

`request_payment(...)` is a stub: the real implementation will compose with
the `payments` app to open a `Payment(purpose=CONCIERGE)` for the chosen
`BookingConciergeItem`. It's exposed now only so the payments service layer
has a stable import target when it lands.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from reservations.enums import ConciergeStatus

if TYPE_CHECKING:
    from reservations.models.concierge import BookingConciergeItem


class ConciergeService:
    """Concierge-line orchestration + the `Booking.adjustment` denorm recompute."""

    @classmethod
    def recompute_adjustment(cls, booking_id: int) -> None:
        """Re-derive `Booking.adjustment` from this booking's non-cancelled
        concierge lines.

        The signal receivers call this on single-row save/delete; bulk callers
        (`queryset.update()`, `bulk_create`, `bulk_update`) must call it
        explicitly because no signal fires for them.
        """
        from reservations.models.booking import Booking
        from reservations.models.concierge import BookingConciergeItem

        # Iterate in Python — concierge lines per booking are bounded (<~50)
        # and this keeps the multiplication portable across SQLite (tests) and
        # Postgres (prod) without resorting to F-expressions with explicit
        # casts.
        items = (
            BookingConciergeItem.objects.filter(booking_id=booking_id)
            .exclude(status=ConciergeStatus.CANCELLED.value)
            .values("unit_price", "quantity")
        )
        total = Decimal("0")
        for item in items:
            total += Decimal(item["unit_price"]) * Decimal(item["quantity"])
        total = total.quantize(Decimal("0.01"))
        Booking.objects.filter(pk=booking_id).update(adjustment=total)

    @classmethod
    def recompute_for_bookings(cls, booking_ids: Iterable[int]) -> None:
        """Recompute `Booking.adjustment` for each distinct booking id.

        The batch entry point for bulk concierge mutations that touch many
        bookings at once.
        """
        for booking_id in set(booking_ids):
            cls.recompute_adjustment(booking_id)

    @classmethod
    def request_payment(
        cls,
        item: BookingConciergeItem,
        *,
        actor: Any = None,
    ) -> None:
        """Open a payment for a concierge line.

        TODO: implement once the payments app lands. The shape is fixed so the
        eventual `payments` service can call back into here without churn.
        """
        raise NotImplementedError(
            "ConciergeService.request_payment requires the payments app — pending"
        )
