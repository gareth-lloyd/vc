"""Background-task entry points for the payments app.

All tasks are written synchronously today; production deployment swaps in
Celery decorators (`@shared_task`) and `*.delay(...)` enqueuing.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from payments.enums import (
    PaymentPurpose,
    PaymentStatus,
    SecurityDepositStatus,
)
from payments.models import Payment, SecurityDeposit
from payments.models.webhook_delivery import WebhookDelivery
from payments.webhooks.base import WebhookDispatcher
from reservations.enums import ACTIVE_BOOKING_STATUSES

if TYPE_CHECKING:
    from reservations.models import Booking


logger = logging.getLogger(__name__)


# Balance-reminder thresholds, ordered most-urgent first. For each row we pick
# the most-urgent threshold whose `(due_date - today).days <= threshold` and
# whose template hasn't already been sent — so a missed cron day still fires
# the right reminder on the next run instead of being silently skipped.
BALANCE_REMINDER_TEMPLATES: tuple[tuple[int, str], ...] = (
    (0, "booking.balance_due_today"),
    (3, "booking.balance_reminder_3d"),
    (7, "booking.balance_reminder_7d"),
)
SECURITY_DEPOSIT_REMINDER_TEMPLATES: tuple[tuple[int, str], ...] = (
    (0, "payment.security_deposit_request"),
    (7, "payment.security_deposit_request"),
)
SECURITY_DEPOSIT_OPEN_STATUSES: frozenset[str] = frozenset(
    {
        SecurityDepositStatus.AWAITING_DETAILS.value,
        SecurityDepositStatus.AWAITING_BT.value,
    }
)


def process_webhook_delivery(delivery_id: int) -> None:
    """Load a persisted delivery and apply its event.

    TODO: convert to a Celery `@shared_task` with autoretry on transient
    exceptions and a Sentry alert after retry exhaustion.
    """
    delivery = WebhookDelivery.objects.get(pk=delivery_id)
    WebhookDispatcher.process(delivery)


def send_payment_reminders(*, now: datetime | None = None) -> int:
    """Dispatch deposit / balance / security-deposit reminder emails.

    Walks PENDING ``Payment`` and open ``SecurityDeposit`` rows for ACTIVE
    bookings whose arrival is today or later, and for each row picks the
    most urgent uncrossed reminder threshold (delta ≤ threshold and template
    not yet sent) — so a single missed cron day still fires the right
    reminder on the next run instead of silently skipping it.

    Idempotent: ``EmailService.send`` keys on ``(template_key, sorted(to),
    correlation)`` (correlation includes a per-row identifier and a
    ``reminder_band`` so the SD T-7 and T-0 emails are distinct logical
    events). Re-running on the same day returns the existing log row.

    Returns the number of dispatch attempts (one per matched row).
    """
    now = now or timezone.now()
    today = now.date()

    sent = 0
    sent += _send_payment_reminders(today)
    sent += _send_security_deposit_reminders(today)
    return sent


def _send_payment_reminders(today: Any) -> int:
    payments = (
        Payment.objects.filter(
            status=PaymentStatus.PENDING.value,
            due_at__isnull=False,
            purpose__in=[
                PaymentPurpose.DEPOSIT.value,
                PaymentPurpose.BALANCE.value,
            ],
            booking__status__in=list(ACTIVE_BOOKING_STATUSES),
            booking__date_from__gte=today,
        )
        .select_related("booking", "booking__guest", "booking__property", "currency")
        .order_by("pk")
    )

    sent = 0
    for payment in payments:
        try:
            band = _payment_reminder_band(payment, today)
            if band is None:
                continue
            template_key, threshold = band
            if _dispatch(
                template_key,
                payment=payment,
                reminder_band=threshold,
            ):
                sent += 1
        except Exception:
            # One bad row must not abort the whole batch — every remaining
            # row deserves its reminder. The exception is captured with
            # context so Sentry / log monitors can surface it.
            logger.exception(
                "send_payment_reminders: failed for payment %s; continuing",
                payment.pk,
            )
    return sent


def _payment_reminder_band(payment: Payment, today: Any) -> tuple[str, int] | None:
    """Pick the most urgent uncrossed reminder threshold for ``payment``."""
    due_date = payment.due_at.date() if payment.due_at else None
    if due_date is None:
        return None
    delta = (due_date - today).days

    if payment.purpose == PaymentPurpose.DEPOSIT.value:
        if delta > 0:
            return None
        if _reminder_already_sent(
            payment_id=payment.pk,
            template_key="payment.reminder.deposit",
            band=0,
        ):
            return None
        return ("payment.reminder.deposit", 0)

    if payment.purpose == PaymentPurpose.BALANCE.value:
        for threshold, template_key in BALANCE_REMINDER_TEMPLATES:
            if delta > threshold:
                continue
            if _reminder_already_sent(
                payment_id=payment.pk,
                template_key=template_key,
                band=threshold,
            ):
                continue
            return (template_key, threshold)
    return None


def _send_security_deposit_reminders(today: Any) -> int:
    deposits = (
        SecurityDeposit.objects.filter(
            status__in=list(SECURITY_DEPOSIT_OPEN_STATUSES),
            due_at__isnull=False,
            booking__status__in=list(ACTIVE_BOOKING_STATUSES),
            booking__date_from__gte=today,
        )
        .select_related("booking", "booking__guest", "booking__property", "currency")
        .order_by("pk")
    )

    sent = 0
    for sd in deposits:
        try:
            band = _sd_reminder_band(sd, today)
            if band is None:
                continue
            template_key, threshold = band
            if _dispatch(
                template_key,
                security_deposit=sd,
                reminder_band=threshold,
            ):
                sent += 1
        except Exception:
            logger.exception(
                "send_payment_reminders: failed for security_deposit %s; continuing",
                sd.pk,
            )
    return sent


def _sd_reminder_band(sd: SecurityDeposit, today: Any) -> tuple[str, int] | None:
    due_date = sd.due_at.date() if sd.due_at else None
    if due_date is None:
        return None
    delta = (due_date - today).days
    for threshold, template_key in SECURITY_DEPOSIT_REMINDER_TEMPLATES:
        if delta > threshold:
            continue
        if _reminder_already_sent(
            security_deposit_id=sd.pk,
            template_key=template_key,
            band=threshold,
        ):
            continue
        return (template_key, threshold)
    return None


def _reminder_already_sent(
    *,
    template_key: str,
    band: int,
    payment_id: int | None = None,
    security_deposit_id: int | None = None,
) -> bool:
    """True when an EmailLog row already exists for this (row, template, band).

    The "band" filter means SD T-7 and T-0 — which share a template_key — are
    treated as distinct logical reminders and dedup independently.
    """
    from comms.enums import EmailLogStatus
    from comms.models import EmailLog

    correlation_filters: dict[str, Any] = {
        "template_key": template_key,
        "correlation__reminder_band": band,
    }
    if payment_id is not None:
        correlation_filters["correlation__payment_id"] = payment_id
    if security_deposit_id is not None:
        correlation_filters["correlation__security_deposit_id"] = security_deposit_id

    return (
        EmailLog.objects.filter(**correlation_filters)
        .exclude(status=EmailLogStatus.FAILED)
        .exists()
    )


def _dispatch(
    template_key: str,
    *,
    payment: Payment | None = None,
    security_deposit: SecurityDeposit | None = None,
    reminder_band: int,
) -> bool:
    """Render context, call ``EmailService.send``, return True on a dispatch.

    Returns False when skipped (no recipient address on file or known
    infra-level error like a missing template / SMTP profile). Unexpected
    exceptions bubble up so the calling loop's per-row handler can log and
    keep going.
    """
    from comms.exceptions import EmailTemplateNotFound, NoSmtpProfileAvailable
    from comms.recipients import guest_email
    from comms.services import EmailService

    if payment is not None:
        booking = payment.booking
        amount = payment.amount
        currency_code = payment.currency.code
        due_at = payment.due_at
        correlation = {
            "booking_id": booking.pk,
            "payment_id": payment.pk,
            "reminder_band": reminder_band,
        }
    elif security_deposit is not None:
        booking = security_deposit.booking
        amount = security_deposit.amount
        currency_code = security_deposit.currency.code
        due_at = security_deposit.due_at
        correlation = {
            "booking_id": booking.pk,
            "security_deposit_id": security_deposit.pk,
            "reminder_band": reminder_band,
        }
    else:
        raise ValueError("send_payment_reminders._dispatch needs payment or security_deposit")

    recipient = guest_email(booking.guest)
    if recipient is None:
        logger.warning(
            "%s skipped: no guest email on booking %s",
            template_key,
            booking.pk,
        )
        return False

    try:
        EmailService.send(
            template_key=template_key,
            context=_reminder_context(
                booking=booking,
                amount=amount,
                currency_code=currency_code,
                due_at=due_at,
                payment=payment,
            ),
            to=[recipient],
            correlation=correlation,
        )
    except (NoSmtpProfileAvailable, EmailTemplateNotFound) as exc:
        logger.warning("Skipping %s reminder: %s", template_key, exc)
        return False
    return True


def _reminder_context(
    *,
    booking: Booking,
    amount: Any,
    currency_code: str,
    due_at: datetime | None,
    payment: Payment | None,
) -> dict[str, Any]:
    return {
        "booking_reference": booking.reference,
        "guest_first_name": booking.guest.first_name,
        "property_name": booking.property.display_name or booking.property.name,
        "date_from": booking.date_from.isoformat(),
        "date_to": booking.date_to.isoformat(),
        "amount": f"{amount:.2f}",
        "currency": currency_code,
        "due_on": due_at.date().isoformat() if due_at else "",
        "payment_reference": payment.reference if payment is not None else "",
    }


def process_sd_refunds() -> None:
    """Walk `SecurityDeposit` rows due for release / refund.

    PRE_AUTH_HOLD past `release_scheduled_for` → `:release` the hold.
    BT_REFUNDABLE past `release_scheduled_for` → open + execute a
    `Refund(purpose_track=SECURITY_DEPOSIT)`.

    TODO: implement the scan + dispatch loop. Flagged for ops review if a
    damage claim is pending against the booking.
    """
