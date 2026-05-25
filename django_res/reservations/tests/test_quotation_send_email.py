"""Tests for the `quotation.sent` lifecycle email."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from accounts.models import Contact, User
from comms.enums import SmtpScope
from comms.models import EmailLog, SmtpProfile
from reservations.models import Quotation

if TYPE_CHECKING:
    from pricing.models import Currency
    from reservations.models import Guest, TermsVersion


@pytest.fixture
def lifecycle_templates(db: None) -> None:
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates()


def _make_quotation(
    guest: Guest, currency: Currency, terms: TermsVersion, agent: Contact | None = None
) -> Quotation:
    return Quotation.objects.create(
        guest=guest,
        agent=agent,
        currency=currency,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )


@pytest.mark.django_db
def test_quotation_send_uses_agent_personal_profile_when_present(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    agent_user = User.objects.create_user(
        email="agent@villa.test",
        password="pw",
        first_name="Ava",
        last_name="Agent",
    )
    agent_contact = Contact.objects.create(
        first_name="Ava",
        last_name="Agent",
        user=agent_user,
    )
    personal = SmtpProfile.objects.create(
        name="Ava Agent",
        scope=SmtpScope.PERSONAL,
        owner=agent_user,
        host="smtp.example.com",
        port=587,
        username="ava",
        encrypted_password="pw",
        use_tls=True,
        from_email="ava@villa.test",
    )

    quotation = _make_quotation(guest, gbp, terms, agent=agent_contact)
    quotation.send()

    log = EmailLog.objects.get(
        template_key="quotation.sent",
        correlation__quotation_id=quotation.pk,
    )
    assert log.smtp_profile == personal
    assert log.sender_user == agent_user
    assert log.to == [guest.email]


@pytest.mark.django_db
def test_quotation_send_falls_back_to_system_when_agent_has_no_profile(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    quotation = _make_quotation(guest, gbp, terms, agent=None)
    quotation.send()

    log = EmailLog.objects.get(
        template_key="quotation.sent",
        correlation__quotation_id=quotation.pk,
    )
    assert log.smtp_profile == system_profile
    assert log.sender_user is None
