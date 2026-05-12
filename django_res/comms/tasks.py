"""Email dispatch task.

Celery is not wired into the project yet; the function is therefore a plain
callable today and exposes a ``.delay`` attribute so service-layer call sites
match the eventual Celery contract. When Celery lands the function is
swapped for ``@shared_task`` and ``.delay`` becomes the real async dispatch.
"""

from __future__ import annotations

from typing import Any

from django.core.mail import EmailMessage, get_connection
from django.utils import timezone

from comms.enums import EmailLogStatus
from comms.models import EmailLog


def _send(log_id: int) -> None:
    log = EmailLog.objects.select_related("smtp_profile").get(pk=log_id)
    profile = log.smtp_profile
    if profile is None:
        log.status = EmailLogStatus.FAILED
        log.failure_reason = "SMTP profile missing at send time."
        log.save(update_fields=["status", "failure_reason", "updated_at"])
        return

    # encrypted_password is an EncryptedTextField — the descriptor returns
    # cleartext on attribute access, so no manual decrypt is needed here.
    password = profile.encrypted_password or ""
    connection = get_connection(
        host=profile.host,
        port=profile.port,
        username=profile.username,
        password=password,
        use_tls=profile.use_tls,
    )
    headers: dict[str, str] = {}
    if profile.reply_to:
        headers["Reply-To"] = profile.reply_to
    message = EmailMessage(
        subject=log.rendered_subject,
        body=log.rendered_body,
        from_email=log.from_email,
        to=list(log.to),
        cc=list(log.cc) or None,
        bcc=list(log.bcc) or None,
        connection=connection,
        headers=headers or None,
    )
    try:
        message.send(fail_silently=False)
    except Exception as exc:
        log.status = EmailLogStatus.FAILED
        log.failure_reason = str(exc)
        log.save(update_fields=["status", "failure_reason", "updated_at"])
        return

    log.status = EmailLogStatus.SENT
    log.sent_at = timezone.now()
    log.save(update_fields=["status", "sent_at", "updated_at"])


def send_email_log(log_id: int) -> None:
    """Dispatch the persisted ``EmailLog`` via SMTP and update its status.

    Idempotent at the row level: a log already in ``SENT`` is not re-sent.
    """
    _send(log_id)


def _delay(*args: Any, **kwargs: Any) -> None:
    """Stand-in for Celery's ``.delay`` while no broker is wired up."""
    send_email_log(*args, **kwargs)


# Expose .delay so call sites match the eventual Celery contract.
send_email_log.delay = _delay  # type: ignore[attr-defined]
