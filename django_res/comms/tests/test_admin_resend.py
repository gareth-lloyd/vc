from __future__ import annotations

import pytest
from django.contrib.admin.sites import site
from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse

from accounts.models import User
from comms.enums import EmailLogStatus
from comms.models import EmailLog, EmailTemplate, SmtpProfile
from comms.services import EmailService


@pytest.fixture
def superuser(db: None) -> User:
    return User.objects.create_superuser(email="admin@example.com", password="pw")


@pytest.fixture
def template(db: None) -> EmailTemplate:
    return EmailTemplate.objects.create(
        key="test.admin.resend",
        version=1,
        subject_template="Subject",
        body_template="Body",
    )


@pytest.fixture
def failed_log(system_profile: SmtpProfile, template: EmailTemplate) -> EmailLog:
    return EmailLog.objects.create(
        template_key=template.key,
        template_version=template.version,
        to=["guest@example.com"],
        from_email=system_profile.from_email,
        smtp_profile=system_profile,
        rendered_subject="Subject",
        rendered_body="Body",
        status=EmailLogStatus.FAILED,
        failure_reason="SMTP timeout",
    )


@pytest.mark.django_db
def test_resend_failed_action_requeues_and_redispatches(
    client: Client,
    superuser: User,
    failed_log: EmailLog,
) -> None:
    client.force_login(superuser)
    changelist_url = reverse("admin:comms_emaillog_changelist")

    response = client.post(
        changelist_url,
        data={
            "action": "resend_blocked_or_failed",
            "_selected_action": [str(failed_log.pk)],
        },
    )

    assert response.status_code == 302
    failed_log.refresh_from_db()
    assert failed_log.status == EmailLogStatus.SENT
    assert failed_log.failure_reason == ""
    assert failed_log.sent_at is not None


@pytest.mark.django_db
def test_resend_failed_action_skips_non_failed_rows(
    client: Client,
    superuser: User,
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    sent_log = EmailLog.objects.create(
        template_key=template.key,
        template_version=template.version,
        to=["guest@example.com"],
        from_email=system_profile.from_email,
        smtp_profile=system_profile,
        rendered_subject="Subject",
        rendered_body="Body",
        status=EmailLogStatus.SENT,
    )

    client.force_login(superuser)
    response = client.post(
        reverse("admin:comms_emaillog_changelist"),
        data={
            "action": "resend_blocked_or_failed",
            "_selected_action": [str(sent_log.pk)],
        },
    )

    assert response.status_code == 302
    sent_log.refresh_from_db()
    assert sent_log.status == EmailLogStatus.SENT


def test_resend_action_is_registered_on_admin() -> None:
    admin_class = site._registry[EmailLog]
    assert "resend_blocked_or_failed" in (admin_class.actions or ())


@pytest.mark.django_db
def test_resend_blocked_action_requeues_blocked_rows(
    client: Client,
    superuser: User,
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    """Bulk-recovery path for rows blocked by the allowlist or dispatch gate."""
    blocked_log = EmailLog.objects.create(
        template_key=template.key,
        template_version=template.version,
        to=["guest@example.com"],
        from_email=system_profile.from_email,
        smtp_profile=system_profile,
        rendered_subject="Subject",
        rendered_body="Body",
        status=EmailLogStatus.BLOCKED,
        failure_reason="EMAIL_REAL_SENDS_ALLOWED is False — refusing SMTP dispatch.",
    )

    client.force_login(superuser)
    response = client.post(
        reverse("admin:comms_emaillog_changelist"),
        data={
            "action": "resend_blocked_or_failed",
            "_selected_action": [str(blocked_log.pk)],
        },
    )

    assert response.status_code == 302
    blocked_log.refresh_from_db()
    assert blocked_log.status == EmailLogStatus.SENT
    assert blocked_log.failure_reason == ""


@pytest.mark.django_db
def test_admin_resend_blocked_dispatches_to_originals_after_allowlist_widens(
    client: Client,
    superuser: User,
    system_profile: SmtpProfile,
    template: EmailTemplate,
) -> None:
    """End-to-end recovery: block-by-allowlist → widen → admin resend → SMTP.

    The BLOCKED row's `to` retains the original recipient list so the bulk
    resend doesn't have to peek into `correlation` to know who to send to.
    """
    # 1. Allowlist blocks everything — row lands BLOCKED with originals on `to`.
    mail.outbox.clear()
    with override_settings(EMAIL_RECIPIENT_ALLOWLIST=["@villacollective.com"]):
        blocked = EmailService.send(
            template_key=template.key,
            context={},
            to=["guest@gmail.com"],
        )
    assert blocked.status == EmailLogStatus.BLOCKED
    assert blocked.to == ["guest@gmail.com"]
    assert len(mail.outbox) == 0

    # 2. Operator widens the allowlist (or removes it) and triggers the
    #    bulk-resend admin action.
    client.force_login(superuser)
    response = client.post(
        reverse("admin:comms_emaillog_changelist"),
        data={
            "action": "resend_blocked_or_failed",
            "_selected_action": [str(blocked.pk)],
        },
    )

    # 3. SMTP receives the original recipient — nothing was lost.
    assert response.status_code == 302
    blocked.refresh_from_db()
    assert blocked.status == EmailLogStatus.SENT
    assert blocked.failure_reason == ""
    assert len(mail.outbox) == 1
    assert list(mail.outbox[0].to) == ["guest@gmail.com"]
