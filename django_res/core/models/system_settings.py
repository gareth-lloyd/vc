"""Global system-wide configuration singleton.

Backs `GET/PATCH /api/v1/system/settings`. Stored as a single row keyed by
`pk=1`; `SystemSettings.get_solo()` creates the row on first access.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from core.models.base import AuditedModel


class SystemSettings(AuditedModel):
    """Singleton row carrying tenant-wide configuration."""

    # Free-form key/value blob — keeps the surface small and forward compatible.
    # Top-level keys are admin-defined; consumers fetch & merge as needed.
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "system settings"
        verbose_name_plural = "system settings"

    def __str__(self) -> str:
        return "System settings"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Enforce singleton — always pk=1."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> SystemSettings:
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"settings": {}})
        return obj
