"""End-to-end allowlist behaviour at the EmailService boundary."""

from __future__ import annotations

import pytest
from django.core import mail
from django.test import override_settings

from comms.enums import EmailLogStatus
from comms.models import EmailTemplate, SmtpProfile
from comms.services import BLOCKED_RECIPIENTS_KEY, EmailService


@pytest.fixture
def template(db: None) -> EmailTemplate:
    return EmailTemplate.objects.create(
        key="test.allowlist",
        version=1,
        subject_template="Hello {{ name }}",
        title="Hi {{ name }}.",
    )


@pytest.mark.django_db
def test_empty_allowlist_passthrough(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    mail.outbox.clear()
    with override_settings(EMAIL_RECIPIENT_ALLOWLIST=[]):
        log = EmailService.send(
            template_key=template.key,
            context={"name": "Ada"},
            to=["guest@example.com"],
        )
    assert log.status == EmailLogStatus.SENT
    assert log.to == ["guest@example.com"]
    assert BLOCKED_RECIPIENTS_KEY not in log.correlation
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_all_recipients_blocked_persists_blocked_log_and_no_dispatch(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    mail.outbox.clear()
    with override_settings(EMAIL_RECIPIENT_ALLOWLIST=["@villacollective.com"]):
        log = EmailService.send(
            template_key=template.key,
            context={"name": "Ada"},
            to=["guest@gmail.com"],
        )
    assert log.status == EmailLogStatus.BLOCKED
    assert log.failure_reason
    # `to` is the source of truth for who the message was *intended* for, so
    # the admin bulk-resend can re-queue a BLOCKED row without losing the
    # recipient list. `correlation[BLOCKED_RECIPIENTS_KEY]` is kept for
    # forensics — both views agree on the recipient set.
    assert log.to == ["guest@gmail.com"]
    assert log.correlation[BLOCKED_RECIPIENTS_KEY] == ["guest@gmail.com"]
    assert log.rendered_subject == "Hello Ada"
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_blocked_log_stores_original_recipients(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    """A BLOCKED row keeps every original recipient (to + cc + bcc) on the row.

    When the allowlist blocks everyone, `EmailLog.to` / `.cc` / `.bcc` must
    still carry the original addresses so the admin bulk-resend action can
    re-queue the row after the allowlist widens.
    """
    mail.outbox.clear()
    with override_settings(EMAIL_RECIPIENT_ALLOWLIST=["@villacollective.com"]):
        log = EmailService.send(
            template_key=template.key,
            context={"name": "Ada"},
            to=["guest@gmail.com"],
            cc=["agent@gmail.com"],
            bcc=["audit@gmail.com"],
        )

    assert log.status == EmailLogStatus.BLOCKED
    assert log.to == ["guest@gmail.com"]
    assert log.cc == ["agent@gmail.com"]
    assert log.bcc == ["audit@gmail.com"]
    # All three lists merged in the correlation blob for forensics.
    assert set(log.correlation[BLOCKED_RECIPIENTS_KEY]) == {
        "guest@gmail.com",
        "agent@gmail.com",
        "audit@gmail.com",
    }
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_partially_blocked_log_stores_only_allowed_recipients(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    """Partial-block is documented as SENT — `log.to` records what was sent.

    Rationale: the message was delivered to the allowed subset. Resending
    only makes sense for the BLOCKED-everyone case (admin widens allowlist
    and re-queues). The blocked addresses still live on
    `correlation[BLOCKED_RECIPIENTS_KEY]` for audit.
    """
    mail.outbox.clear()
    with override_settings(EMAIL_RECIPIENT_ALLOWLIST=["@villacollective.com"]):
        log = EmailService.send(
            template_key=template.key,
            context={"name": "Ada"},
            to=["me@villacollective.com", "leak@gmail.com"],
        )

    assert log.status == EmailLogStatus.SENT
    assert log.to == ["me@villacollective.com"]
    assert log.correlation[BLOCKED_RECIPIENTS_KEY] == ["leak@gmail.com"]


@pytest.mark.django_db
def test_partial_allowlist_filters_recipients(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    mail.outbox.clear()
    with override_settings(EMAIL_RECIPIENT_ALLOWLIST=["@villacollective.com"]):
        log = EmailService.send(
            template_key=template.key,
            context={"name": "Ada"},
            to=["me@villacollective.com"],
            cc=["leak@gmail.com"],
            bcc=["audit@villacollective.com"],
        )
    assert log.status == EmailLogStatus.SENT
    assert log.to == ["me@villacollective.com"]
    assert log.cc == []
    assert log.bcc == ["audit@villacollective.com"]
    assert log.correlation[BLOCKED_RECIPIENTS_KEY] == ["leak@gmail.com"]
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert list(message.to) == ["me@villacollective.com"]
    assert list(message.cc or []) == []


@pytest.mark.django_db
def test_resend_honours_allowlist(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    # First send (no allowlist) creates a SENT log.
    original = EmailService.send(
        template_key=template.key,
        context={"name": "Ada"},
        to=["guest@gmail.com"],
    )
    assert original.status == EmailLogStatus.SENT

    mail.outbox.clear()
    with override_settings(EMAIL_RECIPIENT_ALLOWLIST=["@villacollective.com"]):
        resent = EmailService.resend(original, actor=None)

    assert resent.status == EmailLogStatus.BLOCKED
    # `to` keeps the originals so a second resend after the allowlist
    # widens has something to dispatch to.
    assert resent.to == ["guest@gmail.com"]
    assert resent.correlation[BLOCKED_RECIPIENTS_KEY] == ["guest@gmail.com"]
    assert len(mail.outbox) == 0
