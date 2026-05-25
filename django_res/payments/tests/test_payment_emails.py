"""Round-trip tests for payment lifecycle email orchestration."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.test import override_settings

from comms.models import EmailLog
from payments.enums import PaymentPurpose, PaymentStatus
from payments.models import Payment

if TYPE_CHECKING:
    from comms.models import SmtpProfile
    from pricing.models import Currency
    from reservations.models import Booking


@pytest.fixture
def lifecycle_templates(db: None) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates()


@pytest.fixture
def payment(booking: Booking, gbp: Currency) -> Payment:
    return Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("400.00"),
        currency=gbp,
    )


@pytest.mark.django_db
def test_payment_succeeded_sends_receipt_to_guest(
    payment: Payment,
    booking: Booking,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    payment.transition_to(PaymentStatus.SUCCEEDED.value)

    logs = list(
        EmailLog.objects.filter(
            template_key="payment.receipt",
            correlation__payment_id=payment.pk,
        )
    )
    assert len(logs) == 1
    assert logs[0].to == [booking.guest.email]


@pytest.mark.django_db
@override_settings(OPS_EMAIL_RECIPIENTS=["ops@villa.test"])
def test_payment_failed_sends_to_ops_and_guest(
    payment: Payment,
    booking: Booking,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    payment.transition_to(PaymentStatus.FAILED.value, reason="Card declined")

    ops = list(
        EmailLog.objects.filter(
            template_key="payment.failed",
            correlation__payment_id=payment.pk,
        )
    )
    guest = list(
        EmailLog.objects.filter(
            template_key="payment.failed_guest",
            correlation__payment_id=payment.pk,
        )
    )
    assert len(ops) == 1
    assert ops[0].to == ["ops@villa.test"]
    assert len(guest) == 1
    assert guest[0].to == [booking.guest.email]


@pytest.mark.django_db
@override_settings(OPS_EMAIL_RECIPIENTS=[])
def test_payment_failed_skips_ops_when_no_recipients_configured(
    payment: Payment,
    booking: Booking,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    payment.transition_to(PaymentStatus.FAILED.value, reason="Card declined")

    assert not EmailLog.objects.filter(
        template_key="payment.failed",
        correlation__payment_id=payment.pk,
    ).exists()
    assert EmailLog.objects.filter(
        template_key="payment.failed_guest",
        correlation__payment_id=payment.pk,
    ).exists()


@pytest.mark.django_db
def test_replaying_payment_succeeded_signal_is_idempotent(
    payment: Payment,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    from payments.signals import payment_succeeded

    payment.transition_to(PaymentStatus.SUCCEEDED.value)
    assert (
        EmailLog.objects.filter(
            template_key="payment.receipt",
            correlation__payment_id=payment.pk,
        ).count()
        == 1
    )

    payment_succeeded.send(sender=Payment, payment=payment)

    assert (
        EmailLog.objects.filter(
            template_key="payment.receipt",
            correlation__payment_id=payment.pk,
        ).count()
        == 1
    )
