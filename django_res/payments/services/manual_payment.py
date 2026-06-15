"""`ManualPaymentService` — operator-recorded payment rows (FG-012).

The track-payments POST previously created `Payment` rows in the view; this
service owns the write so the layering convention holds: rows are born
PENDING (settlement goes through `mark_paid` / `transition_to`, never
creation), and an optional `idempotency_key` collapses operator retries onto
the original row instead of racing the one-active-row-per-purpose constraint.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from django.db import transaction

from core.idempotency import find_by_meta_key, stamp_meta
from core.logging.operations import log_operation
from payments.enums import PaymentStatus
from payments.models.payment import Payment
from pricing.services.currency import quantise_money

if TYPE_CHECKING:
    from datetime import datetime
    from decimal import Decimal

    from reservations.models import Booking

logger = structlog.get_logger(__name__)


class ManualPaymentService:
    """Creates the scheduled `Payment` rows behind the track write surface."""

    @classmethod
    @transaction.atomic
    def record(
        cls,
        *,
        booking: Booking,
        purpose: str,
        amount: Decimal,
        payment_method: str = "",
        provider: str = "",
        provider_reference: str = "",
        due_at: datetime | None = None,
        meta: dict[str, Any] | None = None,
        actor: Any = None,
        idempotency_key: str | None = None,
    ) -> Payment:
        """Create a PENDING `Payment(purpose=...)` row on the booking.

        Always born PENDING — a client-supplied status must never mint a
        SUCCEEDED row, because settlement (`:mark-paid` / `:capture`) is what
        writes the PaymentEvent and fires the booking-advance signals.

        Pass `idempotency_key` from operator UIs that may retry: a repeat
        call with the same key + booking + purpose returns the original row
        untouched. Validation lives in `ManualPaymentCreateSerializer` (API)
        — this service trusts its inputs like its siblings do. A duplicate
        active row without a key still raises `IntegrityError` from the
        per-purpose constraint; the view surfaces that as a 409.
        """
        existing = find_by_meta_key(
            Payment.objects.filter(booking=booking, purpose=purpose),
            idempotency_key,
        )
        if existing is not None:
            # Idempotent cache hit — a no-op return, not an operation run.
            return existing

        with log_operation(
            "payment.manual_record",
            logger=logger,
            booking_id=booking.pk,
            purpose=purpose,
            actor_id=getattr(actor, "pk", None),
        ) as ctx:
            payment = Payment.objects.create(
                booking=booking,
                purpose=purpose,
                status=PaymentStatus.PENDING.value,
                amount=quantise_money(amount, booking.currency),
                currency=booking.currency,
                provider=provider,
                provider_reference=provider_reference,
                payment_method=payment_method,
                due_at=due_at,
                meta=stamp_meta(meta, idempotency_key),
            )
            ctx["payment_id"] = payment.pk
            ctx["amount"] = str(payment.amount)
            ctx["currency"] = booking.currency.code
            return payment
