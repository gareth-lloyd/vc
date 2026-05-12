"""`WebhookDelivery` — persist-first inbound webhook log.

The `UniqueConstraint(provider, event_id)` is the idempotency anchor:
provider re-delivery throws `IntegrityError` on insert, which the
dispatcher catches and turns into a 200 with the prior delivery's outcome.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from core.models.base import TimestampedModel
from payments.enums import WebhookProvider


class WebhookDelivery(TimestampedModel):
    """One inbound webhook receipt — verified, persisted, then processed."""

    provider = models.CharField(max_length=24, choices=WebhookProvider.choices)
    event_id = models.CharField(max_length=128)
    signature = models.CharField(max_length=256, blank=True)
    signature_valid = models.BooleanField(default=False)
    raw_body = models.TextField()
    headers = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    payment = models.ForeignKey(
        "payments.Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_deliveries",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "event_id"],
                name="webhookdelivery_unique_provider_event_id",
            ),
        ]
        indexes = [
            models.Index(fields=["provider", "received_at"]),
            models.Index(fields=["signature_valid", "processed_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.event_id}"
