"""Signal receivers for transactional email dispatch.

Receivers translate domain events (booking transitions, quotation sent,
hold expired, payment outcomes) into `EmailService.send` calls. They run
synchronously in the signal sender's transaction; `EmailService` itself
persists the `EmailLog` row and hands dispatch off to Celery, so the
handler returns quickly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.conf import settings

from comms.contexts import booking_context as _booking_context
from comms.contexts import payment_context as _payment_context
from comms.exceptions import EmailTemplateNotFound, NoSmtpProfileAvailable
from comms.recipients import agent_user_for, guest_email, primary_owner_email
from comms.services import TEMPLATE_RENDER_ERRORS, EmailService
from reservations.enums import BookingStatus

if TYPE_CHECKING:
    from reservations.models.booking import Booking, BookingHold
    from reservations.models.owner_block import OwnerBlock
    from reservations.models.quotation import Quotation


logger = logging.getLogger(__name__)


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
        logger.warning("Skipping %s email: %s", template_key, exc)


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
        recipient = guest_email(booking.guest)
        if recipient is None:
            logger.warning(
                "booking.confirmation skipped: no guest email for booking %s",
                booking.pk,
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
                "owner.approval_request skipped: no primary owner on property %s",
                booking.property_id,
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
        recipient = guest_email(booking.guest)
        if recipient is None:
            return
        _safe_send(
            template_key="booking.declined",
            context=_booking_context(booking),
            to=[recipient],
            correlation=_booking_correlation(booking),
        )
    elif to_status == BookingStatus.CANCELLED.value:
        recipient = guest_email(booking.guest)
        if recipient is None:
            return
        _safe_send(
            template_key="booking.cancelled",
            context=_booking_context(booking),
            to=[recipient],
            correlation=_booking_correlation(booking),
        )
    elif to_status == BookingStatus.CHECKED_OUT.value:
        recipient = guest_email(booking.guest)
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
    recipient = guest_email(quotation.guest)
    if recipient is None:
        logger.warning(
            "quotation.sent skipped: no guest email for quotation %s",
            quotation.pk,
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
            logger.warning("Skipping booking.confirmation resend: %s", exc)
        return

    # No prior confirmation log: fall back to a fresh send so an operator
    # can still surface a confirmation for a booking whose lifecycle handler
    # never fired (e.g. PENDING_OWNER_APPROVAL bookings where the operator
    # wants to pre-send while awaiting owner sign-off).
    recipient = guest_email(booking.guest)
    if recipient is None:
        logger.warning(
            "booking.confirmation resend skipped: no guest email for booking %s",
            booking.pk,
        )
        return
    _safe_send(
        template_key="booking.confirmation",
        context=_booking_context(booking),
        to=[recipient],
        correlation=_booking_correlation(booking),
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
            "date_from": hold.date_from.isoformat(),
            "date_to": hold.date_to.isoformat(),
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
            "date_from": block.date_from.isoformat(),
            "date_to": block.date_to.isoformat(),
            "reason": reason,
        },
        to=[recipient],
        correlation={"owner_block_id": block.pk},
    )


def payment_succeeded_handler(
    sender: Any,
    *,
    payment: Any,
    **_: Any,
) -> None:
    """Send the guest receipt for a successful payment."""
    booking = payment.booking
    recipient = guest_email(booking.guest)
    if recipient is None:
        logger.warning(
            "payment.receipt skipped: no guest email for booking %s",
            booking.pk,
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

    guest_recipient = guest_email(booking.guest)
    if guest_recipient is None:
        logger.warning(
            "payment.failed_guest skipped: no guest email for booking %s",
            booking.pk,
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
    recipient = guest_email(booking.guest)
    if recipient is None:
        return
    _safe_send(
        template_key="security_deposit.released",
        context={
            "booking_reference": booking.reference,
            "guest_first_name": booking.guest.first_name,
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
        booking_transitioned,
        hold_expired,
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
