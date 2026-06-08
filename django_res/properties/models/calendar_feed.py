from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel
from integrations.ical.profiles import CalendarFeedPlatform


class PropertyCalendarFeed(AuditedModel):
    """A per-villa public iCal feed URL, polled into owner-availability blocks.

    A property can have **several** feeds (a villa listed on Airbnb + Vrbo +
    Booking.com publishes one each), so this is a child table, not a column on
    `PropertySettings`. The GAP-011 poller fetches every active feed, coalesces
    the busy events across all of a property's feeds, and reflects them as
    `OwnerBlock(source=ICAL)` rows.

    `url` is a **capability URL**: the secret token in it is the only credential
    guarding the owner's full booking calendar. Treat it as a secret — it must
    not be serialized to owner-facing APIs and must never be logged in full
    (log `pk` instead). It is `audit.track`'d as a sensitive field.
    """

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="calendar_feeds",
    )
    url = models.URLField(max_length=500)
    platform = models.CharField(
        max_length=16,
        choices=CalendarFeedPlatform.choices,
        default=CalendarFeedPlatform.OTHER,
    )
    label = models.CharField(max_length=120, blank=True, default="")
    is_active = models.BooleanField(default=True)
    # Lightweight poll-state mirror for the staff admin glance. The richer
    # integration record lives on `integrations.SyncRecord(provider=ICAL)`,
    # upserted by the poller.
    last_polled_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=16, blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["property", "is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["property", "url"],
                name="unique_calendar_feed_url_per_property",
            ),
        ]
        ordering = ["property_id", "id"]

    def __str__(self) -> str:
        return f"Calendar feed #{self.pk} ({self.platform}) on property #{self.property_id}"
