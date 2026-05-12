"""SyncRecord — a generic-FK row tracking the sync state of a domain row.

Keeps integration metadata (provider id, last push/pull, drift status) off
the domain models. See `08-integrations.md` for rationale.
"""

from __future__ import annotations

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from core.models import TimestampedModel
from integrations.enums import SyncDirection, SyncProvider, SyncStatus


class SyncRecord(TimestampedModel):
    """One per (target row, provider). Generic FK to any domain row."""

    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")

    provider = models.CharField(max_length=32, choices=SyncProvider.choices)
    external_id = models.CharField(max_length=128, blank=True, db_index=True)
    external_url = models.URLField(blank=True)
    direction = models.CharField(max_length=16, choices=SyncDirection.choices)
    status = models.CharField(
        max_length=16,
        choices=SyncStatus.choices,
        default=SyncStatus.PENDING,
    )

    last_pushed_at = models.DateTimeField(null=True, blank=True)
    last_pulled_at = models.DateTimeField(null=True, blank=True)
    last_drift_at = models.DateTimeField(null=True, blank=True)

    local_fingerprint = models.CharField(max_length=128, blank=True)
    remote_fingerprint = models.CharField(max_length=128, blank=True)

    error_message = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id", "provider"],
                name="unique_sync_record_per_target_provider",
            ),
            models.UniqueConstraint(
                fields=["provider", "external_id"],
                condition=models.Q(external_id__gt=""),
                name="unique_sync_record_external_id_per_provider",
            ),
        ]
        indexes = [
            models.Index(fields=["provider", "status"]),
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["external_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.content_type_id}:{self.object_id}"
