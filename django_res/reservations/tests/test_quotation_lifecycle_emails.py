"""Round-trip tests for the `quotation.sent` lifecycle email.

Each test drives `Quotation.send()`, which fires the `quotation_sent`
signal that `comms.signals.quotation_sent_handler` listens for. Tests
assert on the persisted `EmailLog` row.

The handler routes through `EmailService.send` with a `sender_user`, so
these tests also pin the personal-SMTP-vs-system fallback path —
nothing else in the lifecycle layer exercises that branch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from accounts.models import Contact, User
from comms.enums import EmailLogStatus, SmtpScope
from comms.models import EmailLog, SmtpProfile
from reservations.enums import QuotationStatus
from reservations.models import Quotation

if TYPE_CHECKING:
    from reservations.models import QuotationLine

# quotation.sent dispatch is deferred to transaction.on_commit; run those hooks
# immediately so these round-trip tests observe the dispatched EmailLog.
pytestmark = pytest.mark.usefixtures("run_on_commit_immediately")


def _logs_for_quotation(quotation: Quotation) -> list[EmailLog]:
    return list(
        EmailLog.objects.filter(
            template_key="quotation.sent",
            correlation__quotation_id=quotation.pk,
        )
    )


@pytest.fixture
def lifecycle_templates(db: None) -> None:
    """Re-seed the on-disk templates so tests don't depend on migrate order."""
    from comms.management.commands.seed_email_templates import sync_templates

    sync_templates()


@pytest.mark.django_db
def test_quotation_send_dispatches_quotation_sent_email(
    quotation_line: QuotationLine,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    quotation = quotation_line.quotation

    quotation.send()

    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.SENT.value
    logs = _logs_for_quotation(quotation)
    assert len(logs) == 1
    assert logs[0].to == [quotation.guest.email]
    assert logs[0].status == EmailLogStatus.SENT


@pytest.mark.django_db
def test_quotation_send_uses_agent_personal_smtp_when_configured(
    quotation_line: QuotationLine,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    agent_user = User.objects.create_user(
        email="agent@example.com",
        password="agent-pw",
        first_name="Aaron",
        last_name="Agent",
    )
    agent_contact = Contact.objects.create(
        first_name="Aaron",
        last_name="Agent",
        user=agent_user,
    )
    personal_profile = SmtpProfile.objects.create(
        name="Aaron personal",
        scope=SmtpScope.PERSONAL,
        owner=agent_user,
        host="smtp.personal.example.com",
        port=587,
        username="aaron",
        encrypted_password="pw",
        use_tls=True,
        from_email="aaron@example.com",
    )
    quotation = quotation_line.quotation
    quotation.agent = agent_contact
    quotation.save(update_fields=["agent", "updated_at"])

    quotation.send()

    logs = _logs_for_quotation(quotation)
    assert len(logs) == 1
    log = logs[0]
    assert log.smtp_profile_id == personal_profile.pk
    assert log.sender_user_id == agent_user.pk
    assert log.from_email == "aaron@example.com"


@pytest.mark.django_db
def test_quotation_send_falls_back_to_system_when_agent_has_no_personal_profile(
    quotation_line: QuotationLine,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    agent_user = User.objects.create_user(
        email="agent-no-profile@example.com",
        password="agent-pw",
    )
    agent_contact = Contact.objects.create(
        first_name="Bea",
        last_name="Agent",
        user=agent_user,
    )
    quotation = quotation_line.quotation
    quotation.agent = agent_contact
    quotation.save(update_fields=["agent", "updated_at"])

    quotation.send()

    logs = _logs_for_quotation(quotation)
    assert len(logs) == 1
    log = logs[0]
    assert log.smtp_profile_id == system_profile.pk
    # SYSTEM profile → no sender_user attached even when an agent user exists.
    assert log.sender_user_id is None


@pytest.mark.django_db
def test_quotation_send_with_no_guest_email_skips_dispatch(
    quotation_line: QuotationLine,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    quotation = quotation_line.quotation
    # Phone-only guest: no email, still contactable (email="" → NULL on save).
    quotation.guest.email = ""
    quotation.guest.phone = "+447911123456"
    quotation.guest.save(update_fields=["email", "phone", "updated_at"])

    quotation.send()

    quotation.refresh_from_db()
    # Transition must still succeed even with no guest email on file.
    assert quotation.status == QuotationStatus.SENT.value
    assert _logs_for_quotation(quotation) == []


@pytest.mark.django_db
def test_quotation_send_with_agent_lacking_user_falls_back_to_system(
    quotation_line: QuotationLine,
    system_profile: SmtpProfile,
    lifecycle_templates: None,
) -> None:
    agent_contact = Contact.objects.create(
        first_name="Carol",
        last_name="Agent",
        # No linked user → agent_user_for() returns None.
    )
    quotation = quotation_line.quotation
    quotation.agent = agent_contact
    quotation.save(update_fields=["agent", "updated_at"])

    quotation.send()

    logs = _logs_for_quotation(quotation)
    assert len(logs) == 1
    assert logs[0].smtp_profile_id == system_profile.pk
    assert logs[0].sender_user_id is None
