"""Tests for the `hold.expired` lifecycle email."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from accounts.models import Contact, User
from comms.models import EmailLog
from reservations.enums import BookingHoldReason
from reservations.models import Quotation
from reservations.models.booking import BookingHold
from reservations.tasks import expire_holds

if TYPE_CHECKING:
    from comms.models import SmtpProfile
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import Guest, TermsVersion


@pytest.fixture
def lifecycle_templates(db: None) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates()


@pytest.mark.django_db
def test_expire_holds_emits_hold_expired_for_quotation_hold(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    agent_user = User.objects.create_user(
        email="agent@villa.test",
        password="pw",
        first_name="Aria",
        last_name="Agent",
    )
    agent = Contact.objects.create(first_name="Aria", last_name="Agent", user=agent_user)
    quotation = Quotation.objects.create(
        guest=guest,
        agent=agent,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    quotation_hold = BookingHold.objects.create(
        property=property_,
        quotation=quotation,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() - timedelta(minutes=1),
        reason=BookingHoldReason.QUOTATION_OPEN,
    )
    operator_block = BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 7, 10),
        date_to=date(2026, 7, 17),
        expires_at=timezone.now() - timedelta(minutes=1),
        reason=BookingHoldReason.OWNER_BLOCK,
    )

    released = expire_holds()

    assert set(released) == {quotation_hold.pk, operator_block.pk}
    logs = list(
        EmailLog.objects.filter(
            template_key="hold.expired",
            correlation__hold_id=quotation_hold.pk,
        )
    )
    assert len(logs) == 1
    assert logs[0].to == [agent_user.email]
    # The operator block has no agent and must not yield an email.
    assert not EmailLog.objects.filter(
        template_key="hold.expired",
        correlation__hold_id=operator_block.pk,
    ).exists()
