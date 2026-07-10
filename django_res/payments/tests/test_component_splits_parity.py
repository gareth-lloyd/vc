"""GAP-077 parity pin: `payment_component_splits` vs `TrackSerializer`.

The split service (reservations, below payments in the spine) duplicates the
track's "scheduled" semantics with string literals — it cannot import
`TrackSerializer`. This test, living in `payments/tests` where both sides are
importable, pins that the duplicated semantics never drift: per purpose, the
component's gross equals the track's `scheduled_amount` and its due date
equals the track's next-due.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from payments.enums import PaymentPurpose, PaymentStatus
from payments.models import Payment
from payments.serializers.track import TERMINAL_NON_ACTIVE_STATUSES, TrackSerializer
from payments.services import PaymentScheduler
from payments.services.payment_scheduler import _SCHEDULE_PURPOSES
from properties.models.finance import PropertyFinance
from reservations.services import owner_finance
from reservations.services.owner_finance import payment_component_splits


def test_duplicated_vocabulary_matches_payments_enums() -> None:
    """Set-equality pin on the duplicated literals themselves — fixture-based
    parity below only samples behaviour, so a re-categorised status (say
    REFUNDED becoming non-scheduled) or a new schedule purpose (INTERIM)
    must fail HERE, not silently drift."""
    assert tuple(owner_finance._SCHEDULE_PURPOSES) == _SCHEDULE_PURPOSES
    assert owner_finance._TERMINAL_NON_ACTIVE == TERMINAL_NON_ACTIVE_STATUSES


@pytest.mark.django_db
def test_split_gross_and_due_at_match_track_semantics(booking: Any, property_: Any) -> None:
    PropertyFinance.objects.get_or_create(property=property_)
    booking.pricing_snapshot = {
        "total": "1400.00",
        "commission": "280.00",
        "tax": "0.00",
        "net_to_owner": "1120.00",
    }
    booking.save(update_fields=["pricing_snapshot"])
    from reservations.models import Booking

    booking = Booking.objects.get(pk=booking.pk)
    PaymentScheduler.create_for_booking(booking)

    # Mutate the schedule into the drift shapes the track view tolerates
    # (respecting the one-active-row-per-purpose constraints): a cancelled
    # deposit row plus its settled replacement, and a waived balance row
    # plus a manual pending one — both still "scheduled" per the track.
    deposit = Payment.objects.get(booking=booking, purpose=PaymentPurpose.DEPOSIT.value)
    deposit.status = PaymentStatus.CANCELLED.value
    deposit.save(update_fields=["status"])
    Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        status=PaymentStatus.SUCCEEDED.value,
        amount=Decimal("400.00"),
        currency=booking.currency,
        due_at=timezone.now() - timedelta(days=1),
    )
    balance = Payment.objects.get(booking=booking, purpose=PaymentPurpose.BALANCE.value)
    balance.status = PaymentStatus.WAIVED.value
    balance.save(update_fields=["status"])
    Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.BALANCE.value,
        status=PaymentStatus.PENDING.value,
        amount=Decimal("150.00"),
        currency=booking.currency,
        due_at=timezone.now() + timedelta(days=10),
    )

    splits = payment_component_splits(booking)

    assert splits is not None and splits != []
    by_purpose = {s["purpose"]: s for s in splits}
    for purpose in (PaymentPurpose.DEPOSIT.value, PaymentPurpose.BALANCE.value):
        track = TrackSerializer.for_booking_purpose(booking=booking, purpose=purpose)
        assert by_purpose[purpose]["gross"] == track["scheduled_amount"], purpose
        assert by_purpose[purpose]["due_at"] == track["due_at"], purpose
        assert by_purpose[purpose]["status"] == track["status"], purpose
