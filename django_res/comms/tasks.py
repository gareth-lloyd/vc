"""Email dispatch tasks.

``send_email_log`` is the per-message SMTP dispatch task; service-layer call
sites enqueue it with ``.delay(log_id)`` (deferred to commit — see
``comms.services.EmailService``). ``requeue_stuck_emails`` is a beat sweep that
re-enqueues rows left in ``QUEUED`` (the broker isn't durable, so a Redis
restart can drop in-flight jobs; the persisted row is the source of truth).
"""

from __future__ import annotations

import smtplib
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils import timezone

from comms.enums import EmailLogStatus
from comms.models import EmailLog

# Grace period before a still-QUEUED EmailLog is considered stuck and
# re-enqueued. Comfortably longer than a normal dispatch so the sweep never
# races a job that's simply mid-flight.
STUCK_EMAIL_GRACE = timedelta(minutes=10)

# SMELL-015 — split transient SMTP failures (retry with backoff) from
# permanent ones (FAILED). Transient: the connection dropped or the host was
# briefly unreachable (`SMTPServerDisconnected`, `SMTPConnectError`,
# socket/`OSError` timeouts), plus 4xx response codes (greylisting, "try
# again later"). Permanent: refused recipient/sender, auth failures, and any
# 5xx response — re-trying those just re-fails. `SMTPResponseException`
# straddles both, so it's classified by its `smtp_code` (4xx vs 5xx) rather
# than its type. The row-level SENT idempotency in `_send` keeps retries safe.
_TRANSIENT_SMTP_EXCEPTIONS = (
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPConnectError,
    OSError,  # ConnectionResetError, TimeoutError, DNS/socket errors
)


def _is_transient_smtp_error(exc: BaseException) -> bool:
    """True when ``exc`` is a retryable (not permanent) SMTP failure."""
    # Auth and refused-address failures are permanent regardless of code.
    if isinstance(
        exc,
        (
            smtplib.SMTPAuthenticationError,
            smtplib.SMTPRecipientsRefused,
            smtplib.SMTPSenderRefused,
        ),
    ):
        return False
    # Any server response is transient only on a 4xx code; 5xx is permanent.
    if isinstance(exc, smtplib.SMTPResponseException):
        return 400 <= exc.smtp_code < 500
    return isinstance(exc, _TRANSIENT_SMTP_EXCEPTIONS)


class TransientEmailError(Exception):
    """Raised to trigger the ``send_email_log`` task's autoretry/backoff."""


def _send(log_id: int) -> None:
    log = EmailLog.objects.select_related("smtp_profile").get(pk=log_id)

    # Row-level idempotency: a SENT row is never re-sent. This is the guard the
    # at-least-once paths rely on — Celery's acks_late re-delivers an in-flight
    # job if the worker dies after message.send() but before the SENT save, and
    # `requeue_stuck_emails` re-dispatches rows left QUEUED — so without this a
    # crash mid-save would surface as a duplicate guest email.
    if log.status == EmailLogStatus.SENT:
        return

    # Second cast-iron gate: even if EMAIL_BACKEND has been mis-pointed at
    # SMTP, refuse to open the socket unless the flag is explicitly True.
    # Mirrors `EMAIL_REAL_SENDS_ALLOWED` defaulted False in settings/base —
    # a rename surfaces as AttributeError rather than a silent gate-closed.
    if not settings.EMAIL_REAL_SENDS_ALLOWED:
        log.status = EmailLogStatus.BLOCKED
        log.failure_reason = "EMAIL_REAL_SENDS_ALLOWED is False — refusing SMTP dispatch."
        log.save(update_fields=["status", "failure_reason", "updated_at"])
        return

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
    message = EmailMultiAlternatives(
        subject=log.rendered_subject,
        body=log.rendered_body,
        from_email=log.from_email,
        to=list(log.to),
        cc=list(log.cc) or None,
        bcc=list(log.bcc) or None,
        connection=connection,
        headers=headers or None,
    )
    if log.rendered_body_html:
        message.attach_alternative(log.rendered_body_html, "text/html")
    try:
        message.send(fail_silently=False)
    except Exception as exc:
        if _is_transient_smtp_error(exc):
            # Leave the row QUEUED and re-raise so the task autoretries with
            # backoff. A blip (greylist, dropped connection) must not burn the
            # message — the SENT-row idempotency guard makes the retry safe.
            raise TransientEmailError(str(exc)) from exc
        log.status = EmailLogStatus.FAILED
        log.failure_reason = str(exc)
        log.save(update_fields=["status", "failure_reason", "updated_at"])
        return

    log.status = EmailLogStatus.SENT
    log.sent_at = timezone.now()
    log.save(update_fields=["status", "sent_at", "updated_at"])


@shared_task(
    autoretry_for=(TransientEmailError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=6,
)
def send_email_log(log_id: int) -> None:
    """Dispatch the persisted ``EmailLog`` via SMTP and update its status.

    Idempotent at the row level: a log already in ``SENT`` is not re-sent.

    Transient SMTP failures (dropped connection, host blip, 4xx greylisting —
    see ``_is_transient_smtp_error``) leave the row ``QUEUED`` and re-raise as
    ``TransientEmailError``, which this task autoretries with exponential
    backoff (mirrors ``payments.tasks.process_webhook_delivery``). Permanent
    failures (5xx, refused address, auth) are recorded as ``FAILED`` on the
    row; the operator resend is the recovery path. After the retries exhaust,
    Celery surfaces the final ``TransientEmailError`` (django-structlog's
    ``task_failed`` is the alert) and ``requeue_stuck_emails`` re-dispatches
    any row left ``QUEUED`` past the grace window.
    """
    _send(log_id)


@shared_task
def requeue_stuck_emails() -> int:
    """Re-enqueue ``QUEUED`` ``EmailLog`` rows older than the grace window.

    The Redis broker is not durable, so a restart can drop queued dispatch
    jobs while the row stays ``QUEUED`` forever. This beat sweep re-``.delay``s
    them. Safe to re-run: ``send_email_log`` no-ops on rows already ``SENT``.
    Returns the number of rows re-enqueued.
    """
    cutoff = timezone.now() - STUCK_EMAIL_GRACE
    stuck = EmailLog.objects.filter(
        status=EmailLogStatus.QUEUED,
        queued_at__lt=cutoff,
    ).values_list("pk", flat=True)
    ids = list(stuck)
    for log_id in ids:
        send_email_log.delay(log_id)
    return len(ids)
