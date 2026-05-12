"""TermsVersion — append-only legal-copy versioning."""

from __future__ import annotations

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from core.models.base import TimestampedModel


class TermsVersion(TimestampedModel):
    """One row per published copy of the booking T&Cs."""

    version = models.CharField(max_length=32, unique=True)
    published_at = models.DateTimeField(null=True, blank=True)
    body_markdown = models.TextField()
    is_current = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_current"],
                condition=Q(is_current=True),
                name="only_one_current_terms_version",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.version

    @transaction.atomic
    def publish(self) -> TermsVersion:
        """Flip `is_current` to True atomically (clears any prior current row)."""
        TermsVersion.objects.filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
        self.is_current = True
        self.published_at = timezone.now()
        self.save(update_fields=["is_current", "published_at", "updated_at"])
        return self
