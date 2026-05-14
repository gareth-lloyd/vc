from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from comms.enums import EmailLogStatus
from core.models.base import TimestampedModel


class EmailLog(TimestampedModel):
    """Append-only persist-first log of every dispatch attempt.

    Created in ``QUEUED`` before the SMTP call so a row exists even if the
    process dies mid-send. Idempotency keyed by ``(template_key,
    template_version, sorted(to), correlation)`` is enforced at the service
    layer rather than via a DB constraint to keep the table append-only.
    """

    template_key = models.CharField(max_length=64)
    template_version = models.PositiveIntegerField()
    to = models.JSONField(default=list)
    cc = models.JSONField(default=list)
    bcc = models.JSONField(default=list)
    from_email = models.EmailField()
    sender_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_email_logs",
    )
    smtp_profile = models.ForeignKey(
        "comms.SmtpProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="email_logs",
    )
    rendered_subject = models.TextField()
    rendered_body = models.TextField()
    rendered_body_html = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=EmailLogStatus.choices,
        default=EmailLogStatus.QUEUED,
    )
    provider_reference = models.CharField(max_length=255, blank=True)
    failure_reason = models.TextField(blank=True)
    attachments = models.JSONField(default=list, blank=True)
    correlation = models.JSONField(default=dict, blank=True)
    # SHA-256 of the canonical idempotency tuple; used to dedupe re-emissions
    # of the same signal without making the table non-append-only.
    idempotency_hash = models.CharField(max_length=64, blank=True, db_index=True)
    queued_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "queued_at"]),
            models.Index(fields=["template_key", "queued_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.template_key} → {self.to} ({self.status})"
