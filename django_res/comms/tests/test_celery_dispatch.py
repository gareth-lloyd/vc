"""Celery wiring: task registration, on_commit deferral, and the stuck sweep.

These tests pin the behaviour added when Celery was wired in: the app object
auto-discovers every app's tasks, ``EmailService.send`` defers dispatch to
commit (so a real worker never reads a row before its transaction commits),
and ``requeue_stuck_emails`` re-enqueues rows the broker may have dropped.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from django.core import mail
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from comms import tasks
from comms.enums import EmailLogStatus
from comms.models import EmailLog, EmailTemplate, SmtpProfile
from comms.services import EmailService
from villacollective.celery import app as celery_app


def _ctx() -> dict[str, str]:
    return {"booking_reference": "BK-CEL", "guest_first_name": "Cal", "property_name": "Villa C"}


@pytest.fixture
def template(db: None) -> EmailTemplate:
    return EmailTemplate.objects.create(
        key="test.celery.confirmation",
        title="Celery Confirmation",
        version=1,
        subject_template="Booking {{ booking_reference }} confirmed",
        body_template_mjml=(
            "<mjml><mj-body><mj-section><mj-column><mj-text>"
            "Hi {{ guest_first_name }} at {{ property_name }}."
            "</mj-text></mj-column></mj-section></mj-body></mjml>"
        ),
    )


# --- registration ---------------------------------------------------------


def test_expected_tasks_are_registered() -> None:
    """autodiscover_tasks picks up each app's tasks.py by dotted name."""
    # Force the discovery the worker does on boot (imports every app's tasks.py).
    celery_app.loader.import_default_modules()
    registered = set(celery_app.tasks)
    for name in (
        "comms.tasks.send_email_log",
        "comms.tasks.requeue_stuck_emails",
        "reservations.tasks.expire_holds",
        "reservations.tasks.ingest_ical_feeds",
        "reservations.tasks.auto_check_out",
        "reservations.tasks.escalate_pending_owner_approvals",
        "payments.tasks.send_payment_reminders",
        "payments.tasks.process_webhook_delivery",
        "integrations.tasks.push_pending",
    ):
        assert name in registered


def test_task_is_directly_callable_and_has_delay() -> None:
    """A @shared_task stays a plain callable AND exposes .delay."""
    assert callable(tasks.send_email_log)
    assert hasattr(tasks.send_email_log, "delay")
    assert hasattr(tasks.requeue_stuck_emails, "delay")


# --- on_commit deferral ---------------------------------------------------


@override_settings(EMAIL_REAL_SENDS_ALLOWED=True)
@pytest.mark.django_db(transaction=True)
def test_send_defers_dispatch_until_commit(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    """Dispatch is deferred: nothing sends inside the open transaction; the
    on_commit hook fires the (eager) dispatch only once the transaction commits.
    """
    mail.outbox.clear()

    with transaction.atomic():
        log = EmailService.send(
            template_key="test.celery.confirmation",
            context=_ctx(),
            to=["guest@example.com"],
            correlation={"booking_id": 99},
        )
        # Still inside the transaction — the worker must not see a send yet.
        assert log.status == EmailLogStatus.QUEUED
        assert mail.outbox == []

    # Transaction committed: the deferred dispatch ran (eager) and sent.
    log.refresh_from_db()
    assert log.status == EmailLogStatus.SENT
    assert [m.to for m in mail.outbox] == [["guest@example.com"]]


# --- requeue_stuck_emails -------------------------------------------------


def _queued_log(profile: SmtpProfile, *, to: str, age: datetime) -> EmailLog:
    return EmailLog.objects.create(
        template_key="test.celery.confirmation",
        template_version=1,
        to=[to],
        from_email=profile.from_email,
        smtp_profile=profile,
        rendered_subject="Booking BK-CEL confirmed",
        rendered_body="Hi Cal.",
        status=EmailLogStatus.QUEUED,
        queued_at=age,
    )


@override_settings(EMAIL_REAL_SENDS_ALLOWED=True)
@pytest.mark.django_db
def test_requeue_stuck_emails_redispatches_old_queued_rows(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    """A QUEUED row older than the grace window is re-sent; fresh rows aren't."""
    now = timezone.now()
    stuck = _queued_log(
        system_profile, to="stuck@example.com", age=now - tasks.STUCK_EMAIL_GRACE * 2
    )
    fresh = _queued_log(system_profile, to="fresh@example.com", age=now)

    mail.outbox.clear()
    requeued = tasks.requeue_stuck_emails()

    assert requeued == 1
    stuck.refresh_from_db()
    assert stuck.status == EmailLogStatus.SENT  # dispatched (eager) by the sweep
    fresh.refresh_from_db()
    assert fresh.status == EmailLogStatus.QUEUED  # inside grace, untouched
    assert [m.to for m in mail.outbox] == [["stuck@example.com"]]


@override_settings(EMAIL_REAL_SENDS_ALLOWED=True)
@pytest.mark.django_db
def test_send_email_log_is_idempotent_on_sent_rows(
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    """A SENT row is never re-sent — the guard the at-least-once paths rely on.

    Covers both the acks_late re-delivery and requeue_stuck_emails re-dispatch
    of a row whose dispatch already completed.
    """
    log = _queued_log(system_profile, to="once@example.com", age=timezone.now())

    tasks.send_email_log(log.pk)  # first dispatch
    log.refresh_from_db()
    assert log.status == EmailLogStatus.SENT
    assert len(mail.outbox) == 1

    tasks.send_email_log(log.pk)  # re-delivery / re-dispatch must no-op
    assert len(mail.outbox) == 1
