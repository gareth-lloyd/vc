"""Background-task entry points for the payments app.

Each task is a plain synchronous function under ``@shared_task`` — directly
callable from the shell/tests (which run eager), enqueued via ``.delay(...)``
in production, or driven by beat (``send_payment_reminders``).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog
from celery import shared_task
from django.utils import timezone

from core.formats import format_date
from payments.enums import (
    PaymentMethod,
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


logger = structlog.get_logger(__name__)


# Balance-reminder thresholds, ordered most-urgent first. For each row we pick
# the most-urgent threshold whose `(due_date - today).days <= threshold` and
# whose band hasn't already been covered — so a missed cron day still fires
# the right reminder on the next run instead of being silently skipped.
BALANCE_REMINDER_TEMPLATES: tuple[tuple[int, str], ...] = (
    (0, "booking.balance_due_today"),
    (3, "booking.balance_reminder_3d"),
    (7, "booking.balance_reminder_7d"),
)
BALANCE_DUE_TODAY_CARD_TEMPLATE = "payment.card_update_request"
SD_REMINDER_TEMPLATE = "payment.security_deposit_request"
SD_EARLY_BAND_THRESHOLD = 7  # days before SD.due_at — heads-up to pay
SD_ARRIVAL_BAND = 0  # anchored on Booking.date_from — last-chance nudge
SECURITY_DEPOSIT_OPEN_STATUSES: frozenset[str] = frozenset(
    {
        SecurityDepositStatus.AWAITING_DETAILS.value,
        SecurityDepositStatus.AWAITING_BT.value,
    }
)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=6,
)
def process_webhook_delivery(self: Any, delivery_id: int) -> None:
    """Load a persisted delivery and apply its event.

    `WebhookDispatcher.process` records permanent failures (unparseable
    body) in-band and re-raises transient ones — those drive the autoretry
    backoff here. After exhaustion django-structlog's `task_failed` is the
    alert, and `sweep_unprocessed_webhook_deliveries` is the safety net.
    `acks_late` already re-queues on a worker crash.
    """
    delivery = WebhookDelivery.objects.get(pk=delivery_id)
    if self.request.retries:
        delivery.retry_count = self.request.retries
        delivery.save(update_fields=["retry_count", "updated_at"])
    WebhookDispatcher.process(delivery)


# Rows older than this without a processed_at stamp are presumed lost between
# the view's enqueue and the broker (or stuck behind exhausted retries).
WEBHOOK_SWEEP_GRACE = timedelta(minutes=15)
WEBHOOK_SWEEP_RETRY_CAP = 8


@shared_task
def sweep_unprocessed_webhook_deliveries() -> int:
    """Re-enqueue signature-valid deliveries that never finished processing.

    Backstop for enqueues lost between persist and broker publish, and for
    deliveries whose retries exhausted on a long transient outage. Rows at
    the retry cap are counted as `stuck` (the ops signal) but left alone.
    """
    cutoff = timezone.now() - WEBHOOK_SWEEP_GRACE
    base = WebhookDelivery.objects.filter(
        signature_valid=True,
        processed_at__isnull=True,
        received_at__lt=cutoff,
    )
    stuck = base.filter(retry_count__gte=WEBHOOK_SWEEP_RETRY_CAP).count()
    requeued = 0
    for delivery_id in base.filter(
        retry_count__lt=WEBHOOK_SWEEP_RETRY_CAP,
    ).values_list("pk", flat=True):
        process_webhook_delivery.delay(delivery_id)
        requeued += 1
    logger.info("webhook.sweep_batch", requeued=requeued, stuck=stuck)
    return requeued


@shared_task
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
            logger.exception("payment.reminder_failed", payment_id=payment.pk)
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
        if _reminder_already_sent(payment_id=payment.pk, band=0):
            return None
        return ("payment.reminder.deposit", 0)

    if payment.purpose == PaymentPurpose.BALANCE.value:
        for threshold, default_template in BALANCE_REMINDER_TEMPLATES:
            if delta > threshold:
                continue
            if _reminder_already_sent(payment_id=payment.pk, band=threshold):
                continue
            template_key = default_template
            # Legacy CC_CARD_UPDATE branch — at the due-today band, a stored
            # card needs a "refresh your card" nudge instead of the generic
            # balance reminder so the tokenised charge later doesn't fail.
            if threshold == 0 and payment.payment_method == PaymentMethod.CARD.value:
                template_key = BALANCE_DUE_TODAY_CARD_TEMPLATE
            return (template_key, threshold)
    return None


def _send_security_deposit_reminders(today: Any) -> int:
    """Walk open SDs and fire the early and/or arrival reminder bands.

    The two bands are independent logical events (the early heads-up
    anchors on ``SecurityDeposit.due_at``; the arrival nudge anchors on
    ``Booking.date_from``), so both can fire on the same tick when both
    are uncrossed.
    """
    deposits = (
        SecurityDeposit.objects.filter(
            status__in=list(SECURITY_DEPOSIT_OPEN_STATUSES),
            booking__status__in=list(ACTIVE_BOOKING_STATUSES),
        )
        .select_related("booking", "booking__guest", "booking__property", "currency")
        .order_by("pk")
    )

    sent = 0
    for sd in deposits:
        try:
            sent += _dispatch_sd_bands(sd, today)
        except Exception:
            logger.exception("payment.reminder_failed", security_deposit_id=sd.pk)
    return sent


def _dispatch_sd_bands(sd: SecurityDeposit, today: Any) -> int:
    sent = 0
    due_date = sd.due_at.date() if sd.due_at else None
    arrival = sd.booking.date_from

    # Early band — heads-up that the SD is coming due.
    if (
        due_date is not None
        and (due_date - today).days <= SD_EARLY_BAND_THRESHOLD
        and not _reminder_already_sent(security_deposit_id=sd.pk, band=SD_EARLY_BAND_THRESHOLD)
        and _dispatch(
            SD_REMINDER_TEMPLATE,
            security_deposit=sd,
            reminder_band=SD_EARLY_BAND_THRESHOLD,
        )
    ):
        sent += 1

    # Arrival band — the legacy `isStayDate` trigger. Anchors on the
    # guest's actual arrival date, not the SD's due date.
    if (
        arrival is not None
        and (arrival - today).days <= SD_ARRIVAL_BAND
        and not _reminder_already_sent(security_deposit_id=sd.pk, band=SD_ARRIVAL_BAND)
        and _dispatch(
            SD_REMINDER_TEMPLATE,
            security_deposit=sd,
            reminder_band=SD_ARRIVAL_BAND,
        )
    ):
        sent += 1

    return sent


def _reminder_already_sent(
    *,
    band: int,
    payment_id: int | None = None,
    security_deposit_id: int | None = None,
) -> bool:
    """True when any reminder has already been logged at this (row, band).

    Dedupe is intentionally band-scoped (not template-scoped) so the BALANCE
    T-0 band, which renders either ``booking.balance_due_today`` or
    ``payment.card_update_request``, never sends both for the same payment.
    """
    from comms.enums import EmailLogStatus
    from comms.models import EmailLog

    correlation_filters: dict[str, Any] = {"correlation__reminder_band": band}
    if payment_id is not None:
        correlation_filters["correlation__payment_id"] = payment_id
    if security_deposit_id is not None:
        correlation_filters["correlation__security_deposit_id"] = security_deposit_id

    return (
        EmailLog.objects.filter(**correlation_filters)
        .exclude(status__in=[EmailLogStatus.FAILED, EmailLogStatus.BLOCKED])
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
            "payment.reminder_skipped",
            template_key=template_key,
            reason="no_guest_email",
            booking_id=booking.pk,
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
        logger.warning("payment.reminder_skipped", template_key=template_key, reason=str(exc))
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
        "date_from": format_date(booking.date_from),
        "date_to": format_date(booking.date_to),
        "amount": f"{amount:.2f}",
        "currency": currency_code,
        "due_on": format_date(due_at) if due_at else "",
        "payment_reference": payment.reference if payment is not None else "",
    }


@shared_task
def process_sd_refunds() -> None:
    """Walk `SecurityDeposit` rows due for release / refund.

    PRE_AUTH_HOLD past `release_scheduled_for` → `:release` the hold.
    BT_REFUNDABLE past `release_scheduled_for` → open + execute a
    `Refund(purpose_track=SECURITY_DEPOSIT)`.

    TODO: implement the scan + dispatch loop. Flagged for ops review if a
    damage claim is pending against the booking.
    """
