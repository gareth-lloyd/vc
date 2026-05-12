"""Reservations app signals.

Defines:
- `booking_transitioned` — fired by every Booking state-machine transition.
- `hold_expired` — fired per BookingHold row that the `expire_holds` task
  has just released past its `expires_at`.

Wires up:
- `EnquiryNote` post_save → emit a `NOTE_ADDED` `EnquiryEvent`.
- `BookingConciergeItem` post_save / post_delete → recompute
  `Booking.adjustment` from non-cancelled concierge items.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import Signal

from reservations.enums import (
    ConciergeStatus,
    EnquiryEventKind,
    EventSource,
)

# ---------------------------------------------------------------------------
# Public signals
# ---------------------------------------------------------------------------

booking_transitioned = Signal()
"""Fired on every Booking state machine transition.

kwargs: sender=Booking, booking, from_status, to_status, actor, source.
"""

hold_expired = Signal()
"""Fired once per BookingHold released by the `expire_holds` Celery task.

kwargs: sender=BookingHold, hold.
"""


# ---------------------------------------------------------------------------
# EnquiryNote → EnquiryEvent (NOTE_ADDED)
# ---------------------------------------------------------------------------


def _enquiry_note_post_save(
    sender: type,
    instance: Any,
    created: bool,
    **_: Any,
) -> None:
    if not created:
        return
    # Local imports to avoid AppConfig import-order issues.
    from reservations.models.enquiry import EnquiryEvent

    EnquiryEvent.objects.create(
        enquiry=instance.enquiry,
        from_status=instance.enquiry.status,
        to_status=instance.enquiry.status,
        kind=EnquiryEventKind.NOTE_ADDED.value,
        actor=instance.author,
        source=EventSource.USER.value,
        meta={"note_id": instance.pk, "kind": instance.kind},
    )


# ---------------------------------------------------------------------------
# BookingConciergeItem → Booking.adjustment recompute
# ---------------------------------------------------------------------------


def _recompute_booking_adjustment(booking_id: int) -> None:
    from reservations.models.booking import Booking
    from reservations.models.concierge import BookingConciergeItem

    # Iterate in Python — concierge lines per booking are bounded (<~50) and
    # this keeps the multiplication portable across SQLite (tests) and
    # Postgres (prod) without resorting to F-expressions with explicit casts.
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


def _concierge_item_changed(sender: type, instance: Any, **_: Any) -> None:
    _recompute_booking_adjustment(instance.booking_id)


# ---------------------------------------------------------------------------
# Registration — bound on import (apps.py ready() imports this module)
# ---------------------------------------------------------------------------


def _connect() -> None:
    from reservations.models.concierge import BookingConciergeItem
    from reservations.models.enquiry import EnquiryNote

    post_save.connect(
        _enquiry_note_post_save,
        sender=EnquiryNote,
        dispatch_uid="reservations.enquiry_note_post_save",
    )
    post_save.connect(
        _concierge_item_changed,
        sender=BookingConciergeItem,
        dispatch_uid="reservations.concierge_item_post_save",
    )
    post_delete.connect(
        _concierge_item_changed,
        sender=BookingConciergeItem,
        dispatch_uid="reservations.concierge_item_post_delete",
    )


_connect()


__all__ = [
    "booking_transitioned",
    "hold_expired",
]
