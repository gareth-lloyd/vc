"""Track serializer — a synthesized view across Payment(purpose=...) rows."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers


class TrackSerializer(serializers.Serializer[None]):
    """A flattened view of a deposit / balance / security track.

    The track is not its own table; it's the set of `Payment` rows for a
    booking sharing a single `purpose`. This serializer renders the summary
    the FE needs without exposing every payment row inline (those are at
    `/bookings/{id}/{track}/payments`).
    """

    booking = serializers.IntegerField()
    purpose = serializers.CharField()
    scheduled_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    due_at = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField()

    @classmethod
    def for_booking_purpose(cls, *, booking: Any, purpose: str) -> dict[str, Any]:
        """Build the dict the serializer renders.

        Materialises the booking+purpose Payment rows once and partitions /
        aggregates in Python — every track GET runs through this so the
        single-query budget matters.
        """
        from payments.enums import PaymentStatus
        from payments.models import Payment

        rows = list(
            Payment.objects.filter(booking=booking, purpose=purpose).order_by("-created_at")
        )
        terminal_non_active = {
            PaymentStatus.CANCELLED.value,
            PaymentStatus.EXPIRED.value,
            PaymentStatus.FAILED.value,
        }
        scheduled = [p for p in rows if p.status not in terminal_non_active]
        scheduled_amount = sum((Decimal(p.amount) for p in scheduled), start=Decimal("0"))
        paid_amount = sum(
            (Decimal(p.amount) for p in rows if p.status == PaymentStatus.SUCCEEDED.value),
            start=Decimal("0"),
        )
        with_due = sorted(
            (p for p in scheduled if p.due_at is not None),
            key=lambda p: p.due_at,  # type: ignore[arg-type,return-value]
        )
        next_due = with_due[0] if with_due else None
        latest = rows[0] if rows else None  # rows are already ordered by -created_at
        return {
            "booking": booking.pk,
            "purpose": purpose,
            "scheduled_amount": scheduled_amount,
            "paid_amount": paid_amount,
            "due_at": next_due.due_at if next_due else None,
            "status": latest.status if latest else "none",
        }
