from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models import Q

from comms.compilers import compile_mjml
from core.models.base import AuditedModel


class EmailTemplate(AuditedModel):
    """Versioned template of record.

    File-based seeds in ``comms/templates/comms/`` are intended as initial
    content; once a row exists in the DB it is the authoritative source.
    Editing in the admin bumps ``version`` and atomically deactivates the
    prior row.

    ``body_template`` is the plaintext alternative carried in every multipart
    message. ``body_template_mjml`` is the editable HTML source (authored as
    MJML); ``body_template_html`` is its compiled output, derived
    automatically on save and treated as read-only by the admin.
    """

    key = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1)
    subject_template = models.TextField()
    body_template = models.TextField()
    body_template_mjml = models.TextField(blank=True)
    body_template_html = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["key", "version"],
                name="unique_template_version",
            ),
            models.UniqueConstraint(
                fields=["key"],
                condition=Q(is_active=True),
                name="one_active_template_per_key",
            ),
        ]
        indexes = [
            models.Index(fields=["key", "is_active"]),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        # body_template_html is derived from body_template_mjml; recompile on
        # every save so the two never drift, even when the source is edited
        # in the admin.
        self.body_template_html = compile_mjml(self.body_template_mjml)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.key} v{self.version}"
