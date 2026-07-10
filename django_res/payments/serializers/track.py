"""Track serializer — a synthesized view across Payment(purpose=...) rows."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from payments.enums import PaymentMethod, PaymentProvider, PaymentStatus

# Statuses whose rows no longer count toward a track's scheduled amount.
# NOT the complement of `ACTIVE_PAYMENT_STATUSES`: REFUNDED and WAIVED rows
# still count as scheduled money. The GAP-077 component split duplicates
# this set as string literals in `reservations.services.owner_finance`
# (spine: reservations must not import payments) — set equality is pinned
# by `payments/tests/test_component_splits_parity.py`.
TERMINAL_NON_ACTIVE_STATUSES = frozenset(
    {
        PaymentStatus.CANCELLED.value,
        PaymentStatus.EXPIRED.value,
        PaymentStatus.FAILED.value,
    }
)


class ManualPaymentCreateSerializer(serializers.Serializer[dict[str, Any]]):
    """Body of `POST /bookings/{id}/{track}/payments`.

    Manual rows are born PENDING — settlement goes through `:mark-paid` /
    `:capture` so every status change carries a PaymentEvent and fires the
    advance signals. A client-supplied `status` is rejected outright rather
    than ignored: silently dropping it would let a caller believe they
    recorded a settled payment.
    """

    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    due_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    provider = serializers.ChoiceField(
        choices=PaymentProvider.choices, required=False, allow_blank=True, default=""
    )
    provider_reference = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=128
    )
    payment_method = serializers.ChoiceField(
        choices=PaymentMethod.choices, required=False, allow_blank=True, default=""
    )
    meta = serializers.JSONField(required=False, default=dict)
    # Operator UIs that may retry (double-click, flaky network) send a key;
    # a repeat POST with the same key returns the original row (FG-012).
    idempotency_key = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=128
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if "status" in self.initial_data:
            raise serializers.ValidationError(
                {
                    "status": [
                        "status is server-managed — manual payments are created "
                        "PENDING; settle them via :mark-paid or :capture."
                    ]
                }
            )
        return attrs


class TrackSerializer(serializers.Serializer[dict[str, Any]]):
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
        from payments.models import Payment

        # `-pk` tie-break: same-microsecond `created_at` pairs (bulk loads,
        # cancel+replace in one transaction) must resolve the "latest row"
        # deterministically, and identically to the GAP-077 component split
        # (`payment_component_splits` keys on (created_at, pk)).
        rows = list(
            Payment.objects.filter(booking=booking, purpose=purpose).order_by("-created_at", "-pk")
        )
        scheduled = [p for p in rows if p.status not in TERMINAL_NON_ACTIVE_STATUSES]
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
