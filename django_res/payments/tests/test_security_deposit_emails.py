"""Round-trip tests for the `security_deposit.released` email."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from comms.models import EmailLog
from payments.enums import SecurityDepositKind, SecurityDepositStatus
from payments.models import SecurityDeposit

if TYPE_CHECKING:
    from comms.models import SmtpProfile
    from pricing.models import Currency
    from reservations.models import Booking


@pytest.fixture
def lifecycle_templates(db: None) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates()


@pytest.mark.django_db
def test_release_emits_security_deposit_released_email(
    booking: Booking,
    gbp: Currency,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    sd = SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.PRE_AUTH_HOLD.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=SecurityDepositStatus.PRE_AUTHED.value,
        hold_expires_at=timezone.now() + timedelta(days=7),
    )

    sd.transition_to_released()

    logs = list(
        EmailLog.objects.filter(
            template_key="security_deposit.released",
            correlation__deposit_id=sd.pk,
        )
    )
    assert len(logs) == 1
    assert logs[0].to == [booking.guest.email]
