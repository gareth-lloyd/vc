"""IntegrationInboundCall — append-only idempotency ledger for inbound calls.

One row per successfully processed inbound request, unique on
`(provider, idempotency_key)`. A repeat delivery (WP-side retry storm, cron
re-fire) replays the recorded response instead of double-writing. Design:
`08-integrations.md` §Idempotency — amended to store the full `response_body`;
the spec's hash-only column cannot replay a response (recorded erratum).
"""

from __future__ import annotations

from django.db import models

from core.models import TimestampedModel
from integrations.enums import SyncProvider


class IntegrationInboundCall(TimestampedModel):
    """Recorded response for one inbound (provider, idempotency_key).

    Rows are append-only (`updated_at` is inert; the base class keeps the
    sibling sync models' shape and an indexed `created_at` for pruning).
    `response_body` must be a plain-JSON dict and must not carry raw PII —
    the design's hash-PII AuditLog duty sits on the endpoint, not here.
    """

    provider = models.CharField(max_length=32, choices=SyncProvider.choices)
    idempotency_key = models.CharField(max_length=128)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField()
    response_body_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "idempotency_key"],
                name="unique_inbound_call_per_provider_key",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.idempotency_key} -> {self.response_status}"
