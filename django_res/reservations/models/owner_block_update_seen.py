"""OwnerBlockUpdateSeen — per-staff-user "seen" mark on an owner-block update.

The presence of a row means that user has seen that update; absence means it is
still unseen for them. Seen is per user (each staff member clears their own),
so the unique key is (update, user). `created_at` from `TimestampedModel` is the
"seen at" timestamp.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models.base import TimestampedModel


class OwnerBlockUpdateSeen(TimestampedModel):
    update = models.ForeignKey(
        "reservations.OwnerBlockUpdate",
        on_delete=models.CASCADE,
        related_name="seen_marks",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["update", "user"],
                name="ownerblockupdateseen_unique_update_user",
            ),
        ]

    def __str__(self) -> str:
        return f"seen update {self.update_id} by user {self.user_id}"
