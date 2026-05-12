from __future__ import annotations

from django.db import models
from django.db.models import Q

from core.models.base import AuditedModel


class EmailTemplate(AuditedModel):
    """Versioned template of record.

    File-based seeds in ``comms/templates/comms/`` are intended as initial
    content; once a row exists in the DB it is the authoritative source.
    Editing in the admin bumps ``version`` and atomically deactivates the
    prior row.
    """

    key = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1)
    subject_template = models.TextField()
    body_template = models.TextField()
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

    def __str__(self) -> str:
        return f"{self.key} v{self.version}"
