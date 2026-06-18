"""Guest preferences — typed soft attributes (bed types, dietary, etc.).

Each `GuestPreference` row attaches one `GuestPreferenceType` to a guest,
optionally scoped to a specific Quotation when the preference was captured
during that quoting flow.
"""

from __future__ import annotations

from django.db import models

from core.models.base import TimestampedModel


class GuestPreferenceType(TimestampedModel):
    name = models.CharField(max_length=128, unique=True)
    is_active = models.BooleanField(default=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class GuestPreference(TimestampedModel):
    guest = models.ForeignKey(
        "reservations.Guest",
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    # GAP-045 Unit 3a: parallel customer FK to the unified Person. Nullable
    # during the expand/contract transition; reads/writes cut over in Unit 3c.
    person = models.ForeignKey(
        "accounts.Person",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="travel_preferences",
    )
    preference_type = models.ForeignKey(
        GuestPreferenceType,
        on_delete=models.PROTECT,
        related_name="+",
    )
    quotation = models.ForeignKey(
        "reservations.Quotation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guest_preferences",
    )
    notes = models.TextField(blank=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["guest", "preference_type", "quotation"],
                name="unique_guest_preference",
            ),
        ]
        ordering = ["guest_id", "preference_type_id"]

    def __str__(self) -> str:
        return f"{self.guest} → {self.preference_type}"
