"""Signal receivers for transactional email dispatch.

Receivers translate domain events (booking transitions, quotation sent,
hold expired, payment outcomes) into `EmailService.send` calls. They run
synchronously in the signal sender's transaction; `EmailService` itself
persists the `EmailLog` row and hands dispatch off to Celery, so the
handler returns quickly.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

import structlog
from botocore.exceptions import ClientError
from django.conf import settings
from django.utils import timezone

from comms.contexts import booking_context as _booking_context
from comms.contexts import contract_context as _contract_context
from comms.contexts import payment_context as _payment_context
from comms.enums import EmailLogStatus
from comms.exceptions import EmailTemplateNotFound, NoSmtpProfileAvailable
from comms.recipients import (
    agent_user_for,
    primary_owner_email,
    recipient_email,
    recipient_first_name,
)
from comms.services import TEMPLATE_RENDER_ERRORS, Attachment, EmailService
from core.formats import format_date
from reservations.enums import BookingStatus

if TYPE_CHECKING:
    from reservations.models.booking import Booking, BookingHold
    from reservations.models.booking_document import BookingDocument
    from reservations.models.owner_block import OwnerBlock
    from reservations.models.quotation import Quotation


logger = structlog.get_logger(__name__)


def _booking_correlation(booking: Booking) -> dict[str, Any]:
    return {"booking_id": booking.pk}


def _safe_send(template_key: str, **kwargs: Any) -> None:
    """Dispatch via `EmailService.send`, swallowing infra-level errors.

    A domain transition must not break because the SMTP/template
    infrastructure isn't ready. Real send failures still surface via
    the `EmailLog.status` audit trail (Celery dispatch records FAILED
    rows); the errors this catches are setup-time misconfigurations
    that would otherwise propagate out of the signal handler and abort
    the transition.

    Template render errors are caught too (belt-and-braces for C1): the
    publish API render-validates a template before it can go active, but a
    row created out-of-band — a fixture, a shell, a future bulk import —
    could still carry a malformed tag. A booking confirmation must not roll
    back because someone fat-fingered the template; degrade to a logged skip.
    """
    try:
        EmailService.send(template_key=template_key, **kwargs)
    except (NoSmtpProfileAvailable, EmailTemplateNotFound, *TEMPLATE_RENDER_ERRORS) as exc:
        logger.warning("comms.email_skipped", template_key=template_key, reason=str(exc))


def _owner_approval_url(booking: Booking) -> str:
    """Stub URL until the owner-portal chunk lands.

    Carries the booking reference so a future signed-link verification
    can locate the row. The frontend route doesn't exist yet — recipients
    will need to be logged in for v1.
    """
    base = getattr(settings, "FRONTEND_URL", "").rstrip("/")
    return f"{base}/owner/approvals/{booking.reference}"


def booking_transitioned_handler(
    sender: Any,
    *,
    from_status: str,
    to_status: str,
    booking: Booking,
    actor: Any | None = None,
    source: str | None = None,
    **_: Any,
) -> None:
    """Dispatch booking-lifecycle emails keyed off the destination status."""
    if to_status == BookingStatus.AWAITING_DEPOSIT.value:
        # Auto-accept or owner approval both land here; guest sees a
        # single confirmation either way.
        recipient = recipient_email(booking.person)
        if recipient is None:
            logger.warning(
                "comms.email_skipped",
                template_key="booking.confirmation",
                reason="no_guest_email",
                booking_id=booking.pk,
            )
            return
        _safe_send(
            template_key="booking.confirmation",
            context=_booking_context(booking),
            to=[recipient],
            correlation=_booking_correlation(booking),
        )
    elif to_status == BookingStatus.PENDING_OWNER_APPROVAL.value:
        recipient = primary_owner_email(booking.property)
        if recipient is None:
            logger.warning(
                "comms.email_skipped",
                template_key="owner.approval_request",
                reason="no_primary_owner",
                property_id=booking.property_id,
            )
            return
        _safe_send(
            template_key="owner.approval_request",
            context={
                **_booking_context(booking),
                "approval_url": _owner_approval_url(booking),
            },
            to=[recipient],
            correlation=_booking_correlation(booking),
        )
    elif to_status == BookingStatus.DECLINED.value:
        recipient = recipient_email(booking.person)
        if recipient is None:
            return
        _safe_send(
            template_key="booking.declined",
            context=_booking_context(booking),
            to=[recipient],
            correlation=_booking_correlation(booking),
        )
    elif to_status == BookingStatus.CANCELLED.value:
        recipient = recipient_email(booking.person)
        if recipient is None:
            return
        _safe_send(
            template_key="booking.cancelled",
            context=_booking_context(booking),
            to=[recipient],
            correlation=_booking_correlation(booking),
        )
    elif to_status == BookingStatus.CHECKED_OUT.value:
        recipient = recipient_email(booking.person)
        if recipient is None:
            return
        _safe_send(
            template_key="booking.checked_out",
            context=_booking_context(booking),
            to=[recipient],
            correlation=_booking_correlation(booking),
        )


def quotation_sent_handler(
    sender: Any,
    *,
    quotation: Quotation,
    subject: str | None = None,
    intro: str | None = None,
    signoff: str | None = None,
    **_: Any,
) -> None:
    """Send the quotation email as the agent when a personal SMTP profile exists.

    `subject`/`intro`/`signoff` are operator copy overrides forwarded from
    `Quotation.send`; they flow through `build_quotation_context` so the
    rendered subject + body reflect the edited copy (and stay identical to the
    operator's preview).
    """
    recipient = recipient_email(quotation.person)
    if recipient is None:
        logger.warning(
            "comms.email_skipped",
            template_key="quotation.sent",
            reason="no_guest_email",
            quotation_id=quotation.pk,
        )
        return
    agent_user = agent_user_for(quotation)
    # The shared render seam assembles the full quote context (line rows,
    # totals, currency, validity, terms HTML, subject) once — the same context
    # the preview modal and copy-to-clipboard consume. It already carries
    # guest_first_name / agent_name / quotation_reference, so the legacy
    # keys keep working.
    from reservations.services.quotation_render import build_quotation_context

    _safe_send(
        template_key="quotation.sent",
        context=build_quotation_context(
            quotation,
            subject=subject,
            intro=intro,
            signoff=signoff,
        ),
        to=[recipient],
        sender_user=agent_user,
        correlation={"quotation_id": quotation.pk},
    )


def booking_confirmation_resend_requested_handler(
    sender: Any,
    *,
    booking: Booking,
    actor: Any | None = None,
    **_: Any,
) -> None:
    """Resend the latest `booking.confirmation` EmailLog, or send fresh.

    Operator-triggered: the `Booking.send_confirmation_email()` action fires
    this signal. Each call mints a new EmailLog row so the audit trail shows
    a distinct send attempt; the comms-level resend endpoint remains the
    place for client-supplied idempotency keys.
    """
    from comms.models import EmailLog

    latest = (
        EmailLog.objects.filter(
            template_key="booking.confirmation",
            correlation__booking_id=booking.pk,
        )
        .order_by("-queued_at", "-id")
        .first()
    )
    if latest is not None:
        try:
            EmailService.resend(latest, actor=actor)
        except (NoSmtpProfileAvailable, EmailTemplateNotFound) as exc:
            logger.warning(
                "comms.email_skipped",
                template_key="booking.confirmation",
                reason=str(exc),
                resend=True,
            )
        return

    # No prior confirmation log: fall back to a fresh send so an operator
    # can still surface a confirmation for a booking whose lifecycle handler
    # never fired (e.g. PENDING_OWNER_APPROVAL bookings where the operator
    # wants to pre-send while awaiting owner sign-off).
    recipient = recipient_email(booking.person)
    if recipient is None:
        logger.warning(
            "comms.email_skipped",
            template_key="booking.confirmation",
            reason="no_guest_email",
            booking_id=booking.pk,
            resend=True,
        )
        return
    _safe_send(
        template_key="booking.confirmation",
        context=_booking_context(booking),
        to=[recipient],
        correlation=_booking_correlation(booking),
    )


# QUEUED (a worker will pick it up) and SENT (eager dispatch already ran)
# both mean the message reached the mail pipeline. BLOCKED (we refused) and
# FAILED (the server refused) must not stamp `sent_to_guest_at`.
_HANDED_TO_MAIL_PIPELINE = frozenset({EmailLogStatus.QUEUED, EmailLogStatus.SENT})

# GAP-094 — the errors a contract send may degrade to a logged skip. Same set
# `_safe_send` swallows: infrastructure that isn't ready must not turn into an
# exception escaping an `on_commit` callback (auto-generation) or a 500 on the
# staff `:send` action.
_CONTRACT_SEND_ERRORS = (
    NoSmtpProfileAvailable,
    EmailTemplateNotFound,
    *TEMPLATE_RENDER_ERRORS,
)

# Reading the stored PDF's size hits storage, so the same failures
# `comms.tasks` classifies at dispatch can happen here at send-request time:
# the object is gone (`FileNotFoundError`), S3 is unreachable or refuses
# (`ClientError`), or the row somehow has no file (`ValueError` from an empty
# `FieldFile`). None of these may escape — the auto path's blanket `except`
# would log `booking_document_failed`, which is untrue (the document generated
# and committed), and the staff `:send` action would 500.
_ATTACHMENT_READ_ERRORS = (OSError, ValueError, ClientError)


def booking_document_send_requested_handler(
    sender: Any,
    *,
    document: BookingDocument,
    actor: Any | None = None,
    **_: Any,
) -> None:
    """Email a generated `BookingDocument` to the guest, with the file attached.

    Resend-or-send, mirroring `booking_confirmation_resend_requested_handler`:
    `EmailService.send` dedupes on `(template_key, to, correlation)` and the
    correlation is stable per document, so a staff resend of the *same*
    document would otherwise return the original row and put no mail on the
    wire. A prior log for this document therefore goes through
    `EmailService.resend` (which copies `attachments` verbatim, so the guest
    gets the same PDF), and only the first send is a fresh `send`.

    `sent_to_guest_at` is stamped when the resulting row reaches the mail
    pipeline — QUEUED **or** SENT. Both are needed: `EmailService.send`
    schedules dispatch on `transaction.on_commit` and then re-reads the row, so
    under `CELERY_TASK_ALWAYS_EAGER` in autocommit (staging, and the
    `on_commit`-scheduled auto-generation path) the callback has already run
    and the row comes back SENT, never QUEUED. An allowlist-BLOCKED row, a
    FAILED one, or a skip leaves the stamp null rather than claiming a delivery
    that never started. Whether the message actually left is the `EmailLog`
    status' job, reachable from the Comms tab via `correlation.document_id`.
    """
    from comms.models import EmailLog

    booking = document.booking
    recipient = recipient_email(booking.person)
    if recipient is None:
        logger.warning(
            "comms.email_skipped",
            template_key="booking.contract",
            reason="no_guest_email",
            booking_id=booking.pk,
            document_id=document.pk,
        )
        return

    # Scoped to *this* recipient, not just this document: `EmailService.resend`
    # re-sends to the original row's addresses, so a contract first sent to a
    # mistyped address and resent after staff corrected the Person would go to
    # the old address again — and stamp as though the guest had it. No prior
    # log for the current address means a fresh send, which the idempotency
    # key (which already includes `to`) correctly treats as a distinct message.
    latest = (
        EmailLog.objects.filter(
            template_key="booking.contract",
            correlation__document_id=document.pk,
            to__contains=[recipient],
        )
        .order_by("-queued_at", "-id")
        .first()
    )

    attachments = []
    if latest is None:
        # Only the fresh send needs it — a resend copies the metadata off the
        # row it is cloning.
        try:
            attachments = [_contract_attachment(document)]
        except _ATTACHMENT_READ_ERRORS as exc:
            logger.warning(
                "comms.email_skipped",
                template_key="booking.contract",
                reason="attachment_unreadable",
                detail=str(exc),
                booking_id=booking.pk,
                document_id=document.pk,
            )
            return

    try:
        if latest is not None:
            log = EmailService.resend(latest, actor=actor)
        else:
            log = EmailService.send(
                template_key="booking.contract",
                context=_contract_context(document),
                to=[recipient],
                attachments=attachments,
                correlation={"booking_id": booking.pk, "document_id": document.pk},
            )
    except _CONTRACT_SEND_ERRORS as exc:
        logger.warning(
            "comms.email_skipped",
            template_key="booking.contract",
            reason=str(exc),
            booking_id=booking.pk,
            document_id=document.pk,
            resend=latest is not None,
        )
        return

    if log.status in _HANDED_TO_MAIL_PIPELINE:
        document.sent_to_guest_at = timezone.now()
        document.save(update_fields=["sent_to_guest_at", "updated_at"])


def _contract_attachment(document: BookingDocument) -> Attachment:
    """Metadata for the stored PDF; `comms.tasks._send` re-reads the bytes.

    `size` is read off storage rather than trusted from the caller — it is
    what the operator sees on the Comms tab, and a stale figure there is worse
    than the one extra HEAD this costs.
    """
    name = document.file.name or ""
    return Attachment(
        filename=PurePosixPath(name).name,
        content_type="application/pdf",
        size=document.file.size,
        storage_key=name,
        storage="documents",
    )


def hold_expired_handler(
    sender: Any,
    *,
    hold: BookingHold,
    **_: Any,
) -> None:
    """Notify the agent on the underlying quotation that the hold lapsed.

    Operator blocks and maintenance holds have no quotation/agent and
    are silently skipped — they aren't customer-facing.
    """
    quotation = getattr(hold, "quotation", None)
    if quotation is None:
        return
    agent_user = agent_user_for(quotation)
    if agent_user is None or not getattr(agent_user, "email", ""):
        return
    _safe_send(
        template_key="hold.expired",
        context={
            "agent_name": f"{agent_user.first_name} {agent_user.last_name}".strip()
            or agent_user.email,
            "quotation_reference": quotation.reference,
            "property_name": hold.property.display_name or hold.property.name,
            "date_from": format_date(hold.date_from),
            "date_to": format_date(hold.date_to),
        },
        to=[agent_user.email],
        correlation={"quotation_id": quotation.pk, "hold_id": hold.pk},
    )


def owner_block_contested_handler(
    sender: Any,
    *,
    block: OwnerBlock,
    actor: Any | None = None,
    reason: str = "",
    **_: Any,
) -> None:
    """Email the property's primary owner that staff have contested a block.

    The block stays APPROVED — this is a notification, not a state change. If
    the property has no primary owner with an email on file, the send is
    skipped (the contest itself already succeeded).
    """
    recipient = primary_owner_email(block.property)
    if not recipient:
        return
    _safe_send(
        template_key="owner_block.contested",
        context={
            "property_name": block.property.display_name or block.property.name,
            "date_from": format_date(block.date_from),
            "date_to": format_date(block.date_to),
            "reason": reason,
        },
        to=[recipient],
        correlation={"owner_block_id": block.pk},
    )


def ical_conflict_detected_handler(
    sender: Any,
    *,
    property: Any,
    date_from: Any,
    date_to: Any,
    conflict_kind: str = "",
    conflict_reference: str = "",
    booking: Any | None = None,
    feed_labels: str = "",
    **_: Any,
) -> None:
    """Alert ops that an imported iCal block clashed with a live VC commitment.

    Routine imports are silent (they hit the OwnerBlockUpdate awareness feed);
    this fires only on the dangerous case — a date VC already committed (a
    confirmed booking or an open quotation) has just been booked on the owner's
    other channel. `conflict_kind`/`conflict_reference` name the clashing
    commitment; for the booking kind the reference falls back to `booking` for
    older senders. Ops-only; skipped when no ops recipients are configured.

    The date range *and the clashing reference* are part of the dedupe
    correlation, so two materially-different clashes on the same property — a
    different range, or a fresh commitment on the same range — are not collapsed
    into one send. A persistent clash (same reference) still dedupes to one email.
    """
    ops_recipients = list(getattr(settings, "OPS_EMAIL_RECIPIENTS", []) or [])
    if not ops_recipients:
        return
    kind = conflict_kind or ("booking" if booking is not None else "")
    reference = conflict_reference or (getattr(booking, "reference", "") if booking else "")
    _safe_send(
        template_key="ical.conflict",
        context={
            "property_name": property.display_name or property.name,
            "date_from": format_date(date_from),
            "date_to": format_date(date_to),
            "feed_labels": feed_labels,
            "conflict_kind": kind,
            "conflict_reference": reference,
        },
        to=ops_recipients,
        correlation={
            "property_id": property.pk,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "conflict_kind": kind,
            "conflict_reference": reference,
            "audience": "ops",
        },
    )


def payment_succeeded_handler(
    sender: Any,
    *,
    payment: Any,
    **_: Any,
) -> None:
    """Send the guest receipt for a successful payment."""
    booking = payment.booking
    recipient = recipient_email(booking.person)
    if recipient is None:
        logger.warning(
            "comms.email_skipped",
            template_key="payment.receipt",
            reason="no_guest_email",
            booking_id=booking.pk,
        )
        return
    _safe_send(
        template_key="payment.receipt",
        context=_payment_context(payment),
        to=[recipient],
        correlation={"booking_id": booking.pk, "payment_id": payment.pk},
    )


def payment_failed_handler(
    sender: Any,
    *,
    payment: Any,
    **_: Any,
) -> None:
    """Notify ops (when configured) and the guest on a failed payment."""
    booking = payment.booking
    context = _payment_context(payment)

    ops_recipients = list(getattr(settings, "OPS_EMAIL_RECIPIENTS", []) or [])
    if ops_recipients:
        _safe_send(
            template_key="payment.failed",
            context=context,
            to=ops_recipients,
            correlation={
                "booking_id": booking.pk,
                "payment_id": payment.pk,
                "audience": "ops",
            },
        )

    guest_recipient = recipient_email(booking.person)
    if guest_recipient is None:
        logger.warning(
            "comms.email_skipped",
            template_key="payment.failed_guest",
            reason="no_guest_email",
            booking_id=booking.pk,
        )
        return
    _safe_send(
        template_key="payment.failed_guest",
        context=context,
        to=[guest_recipient],
        correlation={
            "booking_id": booking.pk,
            "payment_id": payment.pk,
            "audience": "guest",
        },
    )


def security_deposit_released_handler(
    sender: Any,
    *,
    sd: Any,
    **_: Any,
) -> None:
    """Tell the guest their security deposit has been released."""
    booking = sd.booking
    recipient = recipient_email(booking.person)
    if recipient is None:
        return
    _safe_send(
        template_key="security_deposit.released",
        context={
            "booking_reference": booking.reference,
            "guest_first_name": recipient_first_name(booking.person),
            "amount": f"{sd.amount:.2f}",
            "currency": sd.currency.code,
        },
        to=[recipient],
        correlation={"booking_id": booking.pk, "deposit_id": sd.pk},
    )


def _register() -> None:
    """Connect the comms receivers to the source-app signals."""
    from payments.signals import (
        payment_failed,
        payment_succeeded,
        security_deposit_released,
    )
    from reservations.signals import (
        booking_confirmation_resend_requested,
        booking_document_send_requested,
        booking_transitioned,
        hold_expired,
        ical_conflict_detected,
        owner_block_contested,
        quotation_sent,
    )

    booking_transitioned.connect(
        booking_transitioned_handler,
        dispatch_uid="comms.booking_transitioned",
    )
    booking_confirmation_resend_requested.connect(
        booking_confirmation_resend_requested_handler,
        dispatch_uid="comms.booking_confirmation_resend_requested",
    )
    booking_document_send_requested.connect(
        booking_document_send_requested_handler,
        dispatch_uid="comms.booking_document_send_requested",
    )
    quotation_sent.connect(
        quotation_sent_handler,
        dispatch_uid="comms.quotation_sent",
    )
    hold_expired.connect(
        hold_expired_handler,
        dispatch_uid="comms.hold_expired",
    )
    owner_block_contested.connect(
        owner_block_contested_handler,
        dispatch_uid="comms.owner_block_contested",
    )
    ical_conflict_detected.connect(
        ical_conflict_detected_handler,
        dispatch_uid="comms.ical_conflict_detected",
    )
    payment_succeeded.connect(
        payment_succeeded_handler,
        dispatch_uid="comms.payment_succeeded",
    )
    payment_failed.connect(
        payment_failed_handler,
        dispatch_uid="comms.payment_failed",
    )
    security_deposit_released.connect(
        security_deposit_released_handler,
        dispatch_uid="comms.security_deposit_released",
    )
