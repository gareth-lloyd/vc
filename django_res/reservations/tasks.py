"""Reservations Celery beat tasks.

Each task is a plain synchronous function under ``@shared_task``, so it stays
directly callable from management commands / the shell and from tests (which
run eager) while beat drives it on a schedule in production.
"""

from __future__ import annotations

from datetime import timedelta

import structlog
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from reservations.enums import BookingStatus

logger = structlog.get_logger(__name__)


@shared_task
def ingest_ical_feeds() -> list:
    """Poll every active per-villa iCal feed and reconcile owner blocks (GAP-011).

    Synchronous for now (driven by the `ingest_ical` management command / cron);
    wraps with `@shared_task` once Celery + beat land, sized for OTA poll lag.
    Returns the list of per-property results from `ICalIngestService.run`.
    """
    from reservations.services.ical_ingest import ICalIngestService

    results = ICalIngestService.run()
    logger.info(
        "ical.ingest_completed",
        properties=len(results),
        skipped=sum(1 for r in results if getattr(r, "skipped", False)),
    )
    return results


@shared_task
def expire_holds() -> list[int]:
    """Release `BookingHold` rows past `expires_at`.

    Fires the `hold_expired` signal once per row. Returns the list of ids
    that were just released.
    """
    from reservations.models.booking import BookingHold
    from reservations.signals import hold_expired

    now = timezone.now()
    # NULL `expires_at` = indefinite block (owner/maintenance); never reaped.
    due = list(
        BookingHold.objects.filter(
            released_at__isnull=True,
            expires_at__isnull=False,
            expires_at__lt=now,
        )
    )
    if not due:
        return []
    ids = [hold.pk for hold in due]
    BookingHold.objects.filter(pk__in=ids).update(released_at=now)
    for hold in due:
        # Refresh `released_at` on the in-memory copy so signal handlers see
        # the post-update state without an extra DB round-trip.
        hold.released_at = now
        hold_expired.send(sender=BookingHold, hold=hold)
    logger.info("hold.expired_batch", released=len(ids))
    return ids


@shared_task
def escalate_pending_owner_approvals(threshold_hours: int = 24) -> int:
    """Mark stale pending-owner-approval bookings for ops follow-up.

    Returns the number of bookings that would be escalated. The actual
    comms dispatch lands when the `comms` app is wired.
    """
    from reservations.models.booking import Booking

    cutoff = timezone.now() - timedelta(hours=threshold_hours)
    return Booking.objects.filter(
        status=BookingStatus.PENDING_OWNER_APPROVAL.value,
        updated_at__lt=cutoff,
    ).count()


@shared_task
def expire_quotations() -> int:
    """Expire DRAFT/SENT quotations whose `expires_at` has passed.

    Per-row defensive: a racing operator action (accept/cancel landing
    between the queryset and the transition) skips that row rather than
    aborting the batch.
    """
    from core.exceptions import InvalidTransition
    from reservations.enums import QuotationStatus
    from reservations.models.quotation import Quotation

    due = Quotation.objects.filter(
        status__in=(QuotationStatus.DRAFT.value, QuotationStatus.SENT.value),
        expires_at__lt=timezone.now(),
    )
    count = 0
    for quotation in due:
        try:
            quotation.expire()
        except InvalidTransition:
            continue
        count += 1
    if count:
        logger.info("quotation.expired_batch", count=count)
    return count


@shared_task
def expire_bookings() -> int:
    """Expire AWAITING_DEPOSIT bookings whose deposit window has passed.

    The window is `BOOKING_DEPOSIT_EXPIRY_DAYS` of grace from the deposit
    Payment's `due_at` (stamped at confirmation by the scheduler). Without
    this sweeper a guest who never pays holds the villa's dates forever via
    the overlap EXCLUDE constraint.

    The booking's leftover PENDING payment rows are expired by the
    payments-side `booking_transitioned` receiver (payments sits above
    reservations in the import spine, so the dependency points down from
    there, not up from here). The purpose/status literals below match
    `payments.enums` for the same reason.
    """
    from core.exceptions import InvalidTransition
    from reservations.models.booking import Booking

    window = timedelta(days=settings.BOOKING_DEPOSIT_EXPIRY_DAYS)
    due = Booking.objects.filter(
        status=BookingStatus.AWAITING_DEPOSIT.value,
        payments__purpose="deposit",
        payments__status="pending",
        payments__due_at__lt=timezone.now() - window,
    ).distinct()
    count = 0
    for booking in due:
        try:
            booking.expire()
        except InvalidTransition:
            continue
        count += 1
    if count:
        logger.info("booking.expired_batch", count=count)
    return count


@shared_task
def arm_balances() -> int:
    """Advance DEPOSIT_PAID bookings to AWAITING_BALANCE on `balance_due_at`.

    Runs daily before `send_payment_reminders` so a booking arms the same
    morning its first balance reminder could fire.
    """
    from core.exceptions import InvalidTransition
    from reservations.models.booking import Booking

    due = Booking.objects.filter(
        status=BookingStatus.DEPOSIT_PAID.value,
        balance_due_at__isnull=False,
        balance_due_at__lte=timezone.now().date(),
    )
    count = 0
    for booking in due:
        try:
            booking.arm_balance()
        except InvalidTransition:
            continue
        count += 1
    if count:
        logger.info("booking.balance_armed_batch", count=count)
    return count


@shared_task
def auto_check_out() -> int:
    """Transition CHECKED_IN bookings whose `date_to` has passed.

    Returns the number of bookings checked out. Each booking transitions
    via `Booking.check_out()` so the BookingEvent + signal fan-out is
    consistent with manual check-outs.
    """
    from reservations.models.booking import Booking

    today = timezone.now().date()
    qs = Booking.objects.filter(
        status=BookingStatus.CHECKED_IN.value,
        date_to__lte=today,
    )
    count = 0
    for booking in qs:
        booking.check_out()
        count += 1
    if count:
        logger.info("booking.auto_checked_out_batch", count=count)
    return count
