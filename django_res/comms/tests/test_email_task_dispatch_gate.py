"""Dispatch-layer gate: `_send` refuses SMTP unless the flag is True."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core import mail
from django.test import override_settings

from comms.enums import EmailLogStatus
from comms.models import EmailLog, EmailTemplate, SmtpProfile
from comms.services import EmailService
from comms.tasks import _send


@pytest.fixture
def template(db: None) -> EmailTemplate:
    return EmailTemplate.objects.create(
        key="test.dispatch.gate",
        version=1,
        subject_template="x",
        title="x",
    )


@pytest.mark.django_db
def test_dispatch_gate_closed_short_circuits_to_blocked(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    # Manually create a QUEUED log row so we can drive `_send` directly,
    # bypassing the service layer.
    log = EmailLog.objects.create(
        template_key=template.key,
        template_version=template.version,
        to=["me@villacollective.com"],
        cc=[],
        bcc=[],
        from_email=system_profile.from_email,
        sender_user=None,
        smtp_profile=system_profile,
        rendered_subject="x",
        rendered_body="x",
        rendered_body_html="",
        status=EmailLogStatus.QUEUED,
        attachments=[],
        correlation={},
        idempotency_hash="manual-gate-test",
    )

    mail.outbox.clear()
    with (
        override_settings(EMAIL_REAL_SENDS_ALLOWED=False),
        patch("comms.tasks.get_connection") as get_conn,
    ):
        _send(log.pk)

    log.refresh_from_db()
    assert log.status == EmailLogStatus.BLOCKED
    assert "EMAIL_REAL_SENDS_ALLOWED" in log.failure_reason
    get_conn.assert_not_called()
    assert mail.outbox == []


@pytest.mark.django_db
def test_dispatch_gate_open_reaches_smtp(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    """With the flag True and locmem backend, `_send` fills `mail.outbox`."""
    mail.outbox.clear()
    # `override_settings` not needed — test.py already sets the flag True.
    log = EmailService.send(
        template_key=template.key,
        context={},
        to=["me@villacollective.com"],
    )
    assert log.status == EmailLogStatus.SENT
    assert len(mail.outbox) == 1
