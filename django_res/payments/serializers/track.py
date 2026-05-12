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
        """Build the dict the serializer renders."""
        from payments.enums import PaymentStatus
        from payments.models import Payment

        rows = Payment.objects.filter(booking=booking, purpose=purpose)
        scheduled = rows.exclude(
            status__in=(
                PaymentStatus.CANCELLED.value,
                PaymentStatus.EXPIRED.value,
                PaymentStatus.FAILED.value,
            )
        )
        scheduled_amount = sum(
            (Decimal(p.amount) for p in scheduled),
            start=Decimal("0"),
        )
        paid_amount = sum(
            (Decimal(p.amount) for p in rows.filter(status=PaymentStatus.SUCCEEDED.value)),
            start=Decimal("0"),
        )
        next_due = scheduled.exclude(due_at__isnull=True).order_by("due_at").first()
        # Status: the most-recent meaningful row drives it.
        latest = rows.order_by("-created_at").first()
        status = latest.status if latest else "none"
        return {
            "booking": booking.pk,
            "purpose": purpose,
            "scheduled_amount": scheduled_amount,
            "paid_amount": paid_amount,
            "due_at": next_due.due_at if next_due else None,
            "status": status,
        }
