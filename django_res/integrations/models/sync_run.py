"""SyncRun — audit row for a single sync job execution.

Append-only; never deleted. See `00-conventions.md` (audit/event tables).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models import TimestampedModel
from integrations.enums import (
    RunTriggeredBy,
    SyncDirection,
    SyncProvider,
    SyncRunStatus,
)


class SyncRun(TimestampedModel):
    """Audit of a sync job — one row per Celery beat execution."""

    provider = models.CharField(max_length=32, choices=SyncProvider.choices)
    direction = models.CharField(max_length=16, choices=SyncDirection.choices)

    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=16,
        choices=SyncRunStatus.choices,
        default=SyncRunStatus.RUNNING,
    )

    records_processed = models.PositiveIntegerField(default=0)
    records_succeeded = models.PositiveIntegerField(default=0)
    records_failed = models.PositiveIntegerField(default=0)

    triggered_by = models.CharField(
        max_length=16,
        choices=RunTriggeredBy.choices,
        default=RunTriggeredBy.SCHEDULE,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    error_summary = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["provider", "status"]),
            models.Index(fields=["started_at"]),
        ]
