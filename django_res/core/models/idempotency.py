from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def _default_expires_at() -> datetime:
    return timezone.now() + timedelta(hours=24)


class IdempotencyRecord(models.Model):
    """Records (user, path, key, body-hash, response).

    Replaying the same key returns the cached response; replaying with a
    different body returns 409. Nightly cleanup task deletes expired rows.
    """

    key = models.CharField(max_length=128)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="idempotency_records",
    )
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=512)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField()
    response_headers = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(default=_default_expires_at, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "path", "key"],
                name="unique_idempotency_key_per_user_path",
            ),
        ]
