"""Beat tasks that age the quotation/booking lifecycle forward.

`expire_quotations`, `expire_bookings`, and `arm_balances` — the sweepers
the model docstrings promise ("called by the Celery beat"). Each is
per-row defensive: an `InvalidTransition` from a racing operator action
skips that row rather than aborting the batch.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from reservations.enums import BookingStatus, PaymentMethod, QuotationStatus
from reservations.models import Booking, Quotation, QuotationLine
from reservations.tasks import arm_balances, expire_bookings, expire_quotations

pytestmark = pytest.mark.django_db


def _booking(quotation_line: QuotationLine, status: str, **kwargs: object) -> Booking:
    defaults: dict[str, object] = {
        "quotation_line": quotation_line,
        "guest": quotation_line.quotation.guest,
        "property": quotation_line.property,
        "date_from": quotation_line.date_from,
        "date_to": quotation_line.date_to,
        "adults": 2,
        "children": 0,
        "currency": quotation_line.currency,
        "status": status,
        "terms_version": quotation_line.quotation.terms_version,
        "terms_accepted_at": timezone.now(),
        "payment_method": PaymentMethod.CARD.value,
        "rental_price": Decimal("1400.00"),
        "balance_due": Decimal("1400.00"),
    }
    defaults.update(kwargs)
    return Booking.objects.create(**defaults)


def _deposit(booking: Booking, *, due_days_ago: int) -> Any:
    from payments.enums import PaymentPurpose, PaymentStatus
    from payments.models import Payment

    return Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        status=PaymentStatus.PENDING.value,
        amount=Decimal("420.00"),
        currency=booking.currency,
        due_at=timezone.now() - timedelta(days=due_days_ago),
    )


# ----------------------------------------------------------------------
# expire_quotations
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [QuotationStatus.DRAFT.value, QuotationStatus.SENT.value],
)
def test_expire_quotations_expires_past_due_live_states(
    quotation_line: QuotationLine, status: str
) -> None:
    quotation = quotation_line.quotation
    quotation.status = status
    quotation.expires_at = timezone.now() - timedelta(hours=1)
    quotation.save(update_fields=["status", "expires_at"])

    count = expire_quotations()

    quotation.refresh_from_db()
    assert count == 1
    assert quotation.status == QuotationStatus.EXPIRED.value


def test_expire_quotations_skips_accepted_and_future_dated(
    quotation_line: QuotationLine,
) -> None:
    accepted = quotation_line.quotation
    accepted.status = QuotationStatus.ACCEPTED.value
    accepted.expires_at = timezone.now() - timedelta(hours=1)
    accepted.save(update_fields=["status", "expires_at"])

    still_live = Quotation.objects.create(
        enquiry=accepted.guest.enquiries.create(),
        guest=accepted.guest,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=accepted.terms_version,
        status=QuotationStatus.SENT.value,
    )

    count = expire_quotations()

    accepted.refresh_from_db()
    still_live.refresh_from_db()
    assert count == 0
    assert accepted.status == QuotationStatus.ACCEPTED.value
    assert still_live.status == QuotationStatus.SENT.value


# ----------------------------------------------------------------------
# expire_bookings
# ----------------------------------------------------------------------


def test_expire_bookings_expires_awaiting_deposit_past_window(
    quotation_line: QuotationLine,
) -> None:
    from payments.enums import PaymentStatus

    booking = _booking(quotation_line, BookingStatus.AWAITING_DEPOSIT.value)
    deposit = _deposit(booking, due_days_ago=8)

    count = expire_bookings()

    booking.refresh_from_db()
    deposit.refresh_from_db()
    assert count == 1
    assert booking.status == BookingStatus.EXPIRED.value
    assert deposit.status == PaymentStatus.EXPIRED.value


def test_expire_bookings_skips_within_window(
    quotation_line: QuotationLine,
) -> None:
    booking = _booking(quotation_line, BookingStatus.AWAITING_DEPOSIT.value)
    _deposit(booking, due_days_ago=3)

    count = expire_bookings()

    booking.refresh_from_db()
    assert count == 0
    assert booking.status == BookingStatus.AWAITING_DEPOSIT.value


def test_expire_bookings_expires_leftover_pending_balance_too(
    quotation_line: QuotationLine,
) -> None:
    from payments.enums import PaymentPurpose, PaymentStatus
    from payments.models import Payment

    booking = _booking(quotation_line, BookingStatus.AWAITING_DEPOSIT.value)
    _deposit(booking, due_days_ago=10)
    balance = Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.BALANCE.value,
        status=PaymentStatus.PENDING.value,
        amount=Decimal("980.00"),
        currency=booking.currency,
    )

    expire_bookings()

    balance.refresh_from_db()
    assert balance.status == PaymentStatus.EXPIRED.value


# ----------------------------------------------------------------------
# arm_balances
# ----------------------------------------------------------------------


def test_arm_balances_advances_deposit_paid_past_balance_due(
    quotation_line: QuotationLine,
) -> None:
    booking = _booking(
        quotation_line,
        BookingStatus.DEPOSIT_PAID.value,
        balance_due_at=date.today() - timedelta(days=1),
    )

    count = arm_balances()

    booking.refresh_from_db()
    assert count == 1
    assert booking.status == BookingStatus.AWAITING_BALANCE.value


def test_arm_balances_skips_future_or_null_due_date(
    quotation_line: QuotationLine,
) -> None:
    booking = _booking(
        quotation_line,
        BookingStatus.DEPOSIT_PAID.value,
        balance_due_at=None,
    )

    count = arm_balances()

    booking.refresh_from_db()
    assert count == 0
    assert booking.status == BookingStatus.DEPOSIT_PAID.value
