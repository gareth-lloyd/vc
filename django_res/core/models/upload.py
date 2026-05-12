from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def _default_expires_at() -> datetime:
    return timezone.now() + timedelta(hours=1)


class UploadTicket(models.Model):
    """One-shot signed-upload reservation.

    Issued by POST /uploads:sign; consumed by the attach endpoint
    (POST /properties/{id}/images, etc.); cleaned by Celery beat once
    expires_at is past with no consumed_at set.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="upload_tickets",
    )
    path = models.CharField(max_length=512)
    key = models.CharField(max_length=512, unique=True)
    content_type = models.CharField(max_length=128, blank=True)
    max_bytes = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(default=_default_expires_at, db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
