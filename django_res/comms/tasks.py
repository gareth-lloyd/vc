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

from botocore.exceptions import ClientError, HTTPClientError
from botocore.exceptions import ConnectionError as BotoConnectionError
from celery import shared_task
from django.conf import settings
from django.core.files.storage import InvalidStorageError, storages
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


class AttachmentFetchError(Exception):
    """An attachment's bytes could not be read from its storage alias.

    Carries the operator-facing `filename` (the storage key is an opaque
    hashed path) and chains the underlying storage/botocore error as
    `__cause__`, which is what `_is_transient_storage_error` classifies.
    """

    def __init__(self, filename: str, cause: BaseException) -> None:
        super().__init__(f"Attachment {filename!r} could not be read: {cause}")
        self.filename = filename


def _is_transient_storage_error(exc: BaseException) -> bool:
    """True when re-reading the attachment later could plausibly succeed.

    Classified separately from the SMTP errors above, and checked *first*,
    because the two families overlap in exactly the wrong place:
    ``FileNotFoundError`` is an ``OSError``, which ``_is_transient_smtp_error``
    reads as a socket blip. A permanently-absent object would then burn six
    backed-off retries before failing anyway.

    Permanent: the object is gone (``FileNotFoundError``), the alias is not
    configured (``InvalidStorageError`` — a deploy/settings bug), the entry is
    malformed (``KeyError``), or S3 answered with a 4xx (missing key, no
    permission, wrong bucket). Transient: a connection/timeout failure
    reaching the store, or a 5xx from it.
    """
    if isinstance(exc, (FileNotFoundError, InvalidStorageError)):
        return False
    if isinstance(exc, ClientError):
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        return int(status or 0) >= 500
    if isinstance(exc, (BotoConnectionError, HTTPClientError)):
        return True
    return isinstance(exc, OSError)


def _attachment_payloads(log: EmailLog) -> list[tuple[str, bytes, str]]:
    """Re-read every attachment's bytes from its storage alias.

    ``EmailLog.attachments`` is JSON metadata, not a blob — the binary is
    fetched here, at dispatch, so a queued row stays small and a resend
    (which copies the metadata verbatim) re-attaches the same object.

    ``storage`` defaults to ``"default"`` for rows written before the alias
    field existed.
    """
    payloads: list[tuple[str, bytes, str]] = []
    for entry in log.attachments or []:
        # The whole tuple is built inside the `try`: a row missing `filename`
        # or `content_type` would otherwise raise a bare KeyError out of
        # `_send`, which is neither classified nor terminal — the row would
        # stay QUEUED and `requeue_stuck_emails` would re-dispatch it forever.
        try:
            storage = storages[entry.get("storage") or "default"]
            with storage.open(entry["storage_key"]) as handle:
                content = handle.read()
            payloads.append((entry["filename"], content, entry["content_type"]))
        except Exception as exc:
            raise AttachmentFetchError(entry.get("filename", ""), exc) from exc
    return payloads


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

    # Fetch attachment bytes before anything else is built: a permanently
    # missing object must land as FAILED, not as a retry storm (see
    # `_is_transient_storage_error`), and it must not half-open an SMTP
    # connection on the way.
    try:
        attachments = _attachment_payloads(log)
    except AttachmentFetchError as exc:
        cause = exc.__cause__ or exc
        if _is_transient_storage_error(cause):
            raise TransientEmailError(str(exc)) from exc
        log.status = EmailLogStatus.FAILED
        log.failure_reason = str(exc)
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
    for filename, content, content_type in attachments:
        message.attach(filename, content, content_type)
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

    Attachments are metadata on the row; their bytes are re-read from the
    named storage alias at this point (``_attachment_payloads``). A fetch
    failure is classified by ``_is_transient_storage_error`` — a missing
    object or a 4xx is FAILED, a connection failure or 5xx retries — and is
    deliberately checked before the SMTP classifier, which would read
    ``FileNotFoundError`` as a retryable socket error.

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
