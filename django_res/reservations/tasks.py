"""Reservations Celery beat tasks.

Each task is a plain synchronous function under ``@shared_task``, so it stays
directly callable from management commands / the shell and from tests (which
run eager) while beat drives it on a schedule in production.
"""

from __future__ import annotations

from datetime import timedelta

import structlog
from celery import shared_task
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
