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
        body_template="Hi {{ name }}.",
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
    # The original recipient is preserved in correlation for audit;
    # log.to records what *was* sent (nothing).
    assert log.correlation[BLOCKED_RECIPIENTS_KEY] == ["guest@gmail.com"]
    assert log.to == []
    assert log.rendered_subject == "Hello Ada"
    assert len(mail.outbox) == 0


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
    assert resent.correlation[BLOCKED_RECIPIENTS_KEY] == ["guest@gmail.com"]
    assert len(mail.outbox) == 0
