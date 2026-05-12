"""SyncIssue — a specific drift/conflict/error captured during a SyncRun.

Surfaced to ops. Append-only with explicit resolution fields rather than
soft delete (see `00-conventions.md`).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models import TimestampedModel
from integrations.enums import SyncIssueKind, SyncIssueSeverity


class SyncIssue(TimestampedModel):
    run = models.ForeignKey(
        "integrations.SyncRun",
        on_delete=models.CASCADE,
        related_name="issues",
    )
    record = models.ForeignKey(
        "integrations.SyncRecord",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="issues",
    )

    kind = models.CharField(max_length=24, choices=SyncIssueKind.choices)
    severity = models.CharField(
        max_length=16,
        choices=SyncIssueSeverity.choices,
        default=SyncIssueSeverity.WARNING,
    )

    local_state = models.JSONField(default=dict, blank=True)
    remote_state = models.JSONField(default=dict, blank=True)

    message = models.TextField(blank=True)

    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    resolution = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["severity", "resolved_at"]),
            models.Index(fields=["kind", "resolved_at"]),
        ]
