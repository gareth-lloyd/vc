"""SMELL-015 — transient SMTP errors retry; permanent ones fail terminally.

`_send` classifies the exception raised by `message.send()`:

- Transient (connection dropped, host unreachable, socket timeout, 4xx
  greylisting) re-raises so the `send_email_log` task's autoretry/backoff
  kicks in — the row stays QUEUED, not FAILED.
- Permanent (5xx, refused recipient/sender, auth) keeps the terminal
  FAILED + `failure_reason` path.
"""

from __future__ import annotations

import smtplib
from unittest.mock import patch

import pytest

from comms.enums import EmailLogStatus
from comms.models import EmailLog, EmailTemplate, SmtpProfile
from comms.tasks import TransientEmailError, _send


@pytest.fixture
def template(db: None) -> EmailTemplate:
    return EmailTemplate.objects.create(
        key="test.transient.retry",
        version=1,
        subject_template="x",
        title="x",
    )


def _queued_log(template: EmailTemplate, profile: SmtpProfile) -> EmailLog:
    return EmailLog.objects.create(
        template_key=template.key,
        template_version=template.version,
        to=["me@villacollective.com"],
        cc=[],
        bcc=[],
        from_email=profile.from_email,
        sender_user=None,
        smtp_profile=profile,
        rendered_subject="x",
        rendered_body="x",
        rendered_body_html="",
        status=EmailLogStatus.QUEUED,
        attachments=[],
        correlation={},
        idempotency_hash="manual-transient-test",
    )


TRANSIENT_ERRORS = [
    smtplib.SMTPServerDisconnected("connection reset"),
    smtplib.SMTPConnectError(421, b"try again later"),
    smtplib.SMTPResponseException(451, b"greylisted, try later"),
    TimeoutError("timed out"),
    ConnectionResetError("connection reset by peer"),
]

PERMANENT_ERRORS = [
    smtplib.SMTPRecipientsRefused({"bad@nowhere": (550, b"no such user")}),
    smtplib.SMTPSenderRefused(550, b"sender rejected", "from@x"),
    smtplib.SMTPResponseException(550, b"mailbox unavailable"),
    smtplib.SMTPAuthenticationError(535, b"auth failed"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("exc", TRANSIENT_ERRORS, ids=lambda e: type(e).__name__)
def test_transient_error_reraises_and_leaves_log_unfailed(
    system_profile: SmtpProfile,
    template: EmailTemplate,
    exc: Exception,
) -> None:
    log = _queued_log(template, system_profile)

    with (
        patch("comms.tasks.get_connection"),
        patch(
            "comms.tasks.EmailMultiAlternatives.send",
            side_effect=exc,
        ),
    ):
        with pytest.raises(TransientEmailError):
            _send(log.pk)

    log.refresh_from_db()
    assert log.status == EmailLogStatus.QUEUED


@pytest.mark.django_db
@pytest.mark.parametrize("exc", PERMANENT_ERRORS, ids=lambda e: type(e).__name__)
def test_permanent_error_marks_failed(
    system_profile: SmtpProfile,
    template: EmailTemplate,
    exc: Exception,
) -> None:
    log = _queued_log(template, system_profile)

    with (
        patch("comms.tasks.get_connection"),
        patch(
            "comms.tasks.EmailMultiAlternatives.send",
            side_effect=exc,
        ),
    ):
        _send(log.pk)

    log.refresh_from_db()
    assert log.status == EmailLogStatus.FAILED
    assert log.failure_reason


@pytest.mark.django_db
def test_send_email_log_task_has_autoretry() -> None:
    """The task wraps `_send` with Celery autoretry on transient errors."""
    from comms.tasks import send_email_log

    # The shared_task decorator stores retry config on the task object.
    assert send_email_log.max_retries and send_email_log.max_retries > 0
    assert TransientEmailError in send_email_log.autoretry_for
