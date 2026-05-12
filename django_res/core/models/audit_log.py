from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class AuditLog(models.Model):
    """Append-only diff log keyed by content type + object id.

    Models opt in via core.audit.track(Model, fields=[...]). The pre_save
    signal emits one row per save with the changed-field diff. Fields tagged
    sensitive are written with a "[REDACTED]" sentinel rather than cleartext.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.CharField(max_length=64)
    target = GenericForeignKey("content_type", "object_id")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    field_diffs = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    correlation_id = models.UUIDField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["content_type", "object_id", "created_at"]),
            models.Index(fields=["actor", "created_at"]),
        ]
