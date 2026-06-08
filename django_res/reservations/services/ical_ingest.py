"""ICalIngestService — poll per-villa iCal feeds into owner-availability blocks.

Lives in `reservations` (not `integrations`) because it creates `OwnerBlock`
rows: the spine layering forbids `integrations -> reservations`, so the
reconciliation that turns feeds into blocks sits here and imports *down* into the
pure parser (`integrations.ical`), the feed model (`properties`), and
`integrations.SyncRecord`.

Reconciliation model (per property):
1. Fetch + parse every active feed.
2. Coalesce all busy events across the property's feeds into disjoint ranges —
   the same booking arriving via two feeds, and back-to-back bookings, both
   merge, so we never try to place two overlapping holds.
3. Diff the coalesced ranges (keyed by the range itself, not the unstable iCal
   UID) against the property's existing APPROVED `source=ICAL` blocks: create the
   missing, cancel the vanished, leave the unchanged. Re-running with an
   unchanged feed is a no-op.

Resilience: a feed fetch/parse error is recorded on the feed and its SyncRecord
and never aborts the run. If *any* active feed for a property fails, the whole
property is skipped this run — reconciling from a partial view would wrongly
cancel the failed feed's blocks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

import httpx
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from core.exceptions import HoldUnavailable, OverlappingBooking
from integrations.enums import SyncDirection, SyncProvider, SyncStatus
from integrations.ical import (
    BusyInterval,
    coalesce_intervals,
    normalize_feed_url,
    parse_busy_intervals,
    resolve_profile,
)
from integrations.models import SyncRecord
from reservations.enums import BookingHoldReason, OwnerBlockSource, OwnerBlockStatus
from reservations.models import BookingHold, OwnerBlock
from reservations.services.owner_block import OwnerBlockService
from reservations.signals import ical_conflict_detected

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from properties.models import Property, PropertyCalendarFeed

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 20.0


@dataclass
class FeedResult:
    feed_id: int
    ok: bool
    interval_count: int = 0
    error: str = ""


@dataclass
class PropertyResult:
    property_id: int
    skipped: bool = False
    created: int = 0
    cancelled: int = 0
    conflicts: int = 0
    skipped_holds: int = 0
    feeds: list[FeedResult] = field(default_factory=list)


def _range_key(date_from: date, date_to: date) -> str:
    """Stable identity for a coalesced busy range — block identity, not UID."""
    return f"{date_from.isoformat()}_{date_to.isoformat()}"


class ICalIngestService:
    """Reconcile owner-availability blocks against per-villa iCal feeds."""

    @classmethod
    def run(cls, *, properties: QuerySet[Property] | None = None) -> list[PropertyResult]:
        """Poll feeds for the given properties (default: all). Returns per-property results."""
        from properties.models import Property

        base = Property.objects.all() if properties is None else properties
        results: list[PropertyResult] = []
        for prop in base.prefetch_related("calendar_feeds"):
            feeds = [feed for feed in prop.calendar_feeds.all() if feed.is_active]
            if not feeds:
                continue
            try:
                results.append(cls._sync_property(prop, feeds))
            except Exception:  # one villa must not abort the batch
                logger.exception("iCal: unexpected error syncing property %s", prop.pk)
        return results

    @classmethod
    def _sync_property(cls, prop: Property, feeds: list[PropertyCalendarFeed]) -> PropertyResult:
        result = PropertyResult(property_id=prop.pk)
        intervals: list[BusyInterval] = []
        for feed in feeds:
            feed_result, feed_intervals = cls._fetch_and_parse(feed)
            result.feeds.append(feed_result)
            intervals.extend(feed_intervals)

        if not all(fr.ok for fr in result.feeds):
            # Partial view: cancelling from it would drop the failed feed's
            # blocks. Skip the whole property; a later run reconciles cleanly.
            result.skipped = True
            logger.warning(
                "iCal: a feed failed for property %s; skipping reconcile this run",
                prop.pk,
            )
            return result

        merged = coalesce_intervals(intervals)
        cls._reconcile(prop, merged, feeds, result)
        return result

    @classmethod
    def _fetch_and_parse(cls, feed: PropertyCalendarFeed) -> tuple[FeedResult, list[BusyInterval]]:
        url = normalize_feed_url(feed.url)
        profile = resolve_profile(feed.platform, url=url)
        try:
            response = httpx.get(url, timeout=_HTTP_TIMEOUT, follow_redirects=True)
            response.raise_for_status()
            intervals = parse_busy_intervals(response.text, profile)
        except (httpx.HTTPError, ValueError) as exc:  # record + continue, never crash the run
            error = str(exc)[:500]
            # Log the feed id, never the URL (it carries the secret token).
            logger.warning("iCal: feed %s failed: %s", feed.pk, error)
            cls._mark_feed(feed, ok=False, error=error)
            return FeedResult(feed_id=feed.pk, ok=False, error=error), []

        cls._mark_feed(feed, ok=True, error="")
        return FeedResult(feed_id=feed.pk, ok=True, interval_count=len(intervals)), intervals

    @classmethod
    def _reconcile(
        cls,
        prop: Property,
        merged: list[tuple[date, date]],
        feeds: list[PropertyCalendarFeed],
        result: PropertyResult,
    ) -> None:
        existing = {
            block.idempotency_key: block
            for block in OwnerBlock.objects.filter(
                property=prop,
                source=OwnerBlockSource.ICAL.value,
                status=OwnerBlockStatus.APPROVED.value,
            )
            if block.idempotency_key
        }
        desired = {_range_key(start, end): (start, end) for start, end in merged}

        labels = cls._feed_labels(feeds)
        notes = f"Imported from calendar feed(s): {labels}" if labels else "Imported from iCal feed"

        # Cancel before create: an edited range (e.g. extending [Jul1,Jul5) to
        # [Jul1,Jul6)) keys differently, so the old block must release its hold
        # first or the new range collides with it (HoldUnavailable) and the dates
        # are left unblocked for a whole poll cycle. Coalescing guarantees desired
        # ranges are disjoint, so create-after-cancel never self-collides.
        for key, block in existing.items():
            if key not in desired:
                OwnerBlockService.cancel(block, actor=None)
                result.cancelled += 1

        for key, (start, end) in desired.items():
            if key in existing:
                continue
            cls._create_one(prop, start, end, key, notes, labels, result)

    @classmethod
    def _create_one(
        cls,
        prop: Property,
        start: date,
        end: date,
        key: str,
        notes: str,
        labels: str,
        result: PropertyResult,
    ) -> None:
        try:
            OwnerBlockService.create_imported(
                property=prop,
                date_from=start,
                date_to=end,
                idempotency_key=key,
                notes=notes,
            )
            result.created += 1
        except OverlappingBooking as exc:
            # A date VC already sold has been booked on the owner's other
            # channel. Don't write over the booking — alert ops.
            booking = exc.booking
            result.conflicts += 1
            ical_conflict_detected.send(
                sender=None,
                property=prop,
                date_from=start,
                date_to=end,
                booking=booking,
                conflict_kind="booking",
                conflict_reference=getattr(booking, "reference", "") if booking else "",
                feed_labels=labels,
            )
        except HoldUnavailable:
            # Overlaps a live hold. An open-quotation hold is a real double-sell
            # risk — VC is quoting dates the owner just booked elsewhere — so it
            # escalates like a booking clash. Owner-side holds (manual block /
            # maintenance) are benign; the operator owns them, so skip quietly.
            quotation_hold = cls._clashing_quotation_hold(prop, start, end)
            if quotation_hold is None:
                result.skipped_holds += 1
                logger.info(
                    "iCal: range %s..%s on property %s overlaps an existing hold; skipped",
                    start,
                    end,
                    prop.pk,
                )
                return
            quotation = quotation_hold.quotation
            reference = (
                quotation.reference if quotation is not None else f"hold-{quotation_hold.pk}"
            )
            result.conflicts += 1
            ical_conflict_detected.send(
                sender=None,
                property=prop,
                date_from=start,
                date_to=end,
                booking=None,
                conflict_kind="quotation",
                conflict_reference=reference,
                feed_labels=labels,
            )

    @staticmethod
    def _clashing_quotation_hold(prop: Property, start: date, end: date) -> BookingHold | None:
        """The first live open-quotation hold overlapping the range, if any.

        After cancel-before-create (`_reconcile`) the only `HoldUnavailable` a new
        range hits is a *foreign* hold, so a `QUOTATION_OPEN` match here is an
        unambiguous double-sell signal rather than our own block.
        """
        return (
            BookingHold.live_overlapping(property=prop, date_from=start, date_to=end)
            .filter(reason=BookingHoldReason.QUOTATION_OPEN.value)
            .first()
        )

    @staticmethod
    def _feed_labels(feeds: list[PropertyCalendarFeed]) -> str:
        parts = [feed.label or feed.get_platform_display() for feed in feeds]
        # Preserve order, drop duplicates.
        return ", ".join(dict.fromkeys(parts))

    @classmethod
    def _mark_feed(cls, feed: PropertyCalendarFeed, *, ok: bool, error: str) -> None:
        now = timezone.now()
        feed.last_polled_at = now
        feed.last_status = "ok" if ok else "error"
        feed.last_error = error
        feed.save(update_fields=["last_polled_at", "last_status", "last_error", "updated_at"])
        cls._update_sync_record(feed, ok=ok, error=error, when=now)

    @staticmethod
    def _update_sync_record(feed: PropertyCalendarFeed, *, ok: bool, error: str, when: Any) -> None:
        from properties.models import PropertyCalendarFeed as FeedModel

        content_type = ContentType.objects.get_for_model(FeedModel)
        record, _ = SyncRecord.objects.get_or_create(
            content_type=content_type,
            object_id=feed.pk,
            provider=SyncProvider.ICAL.value,
            defaults={
                "direction": SyncDirection.PULL.value,
                "status": SyncStatus.PENDING.value,
            },
        )
        record.status = SyncStatus.IN_SYNC.value if ok else SyncStatus.ERROR.value
        record.last_pulled_at = when
        record.error_message = error
        record.save(update_fields=["status", "last_pulled_at", "error_message", "updated_at"])
