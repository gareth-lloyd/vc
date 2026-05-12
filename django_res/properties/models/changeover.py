from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel
from properties.enums import PrefilledChangeOverDay


class ChangeOverRule(AuditedModel):
    """Per-property override of the default changeover day for a date window.

    A property's `PropertySettings.changeover_day` is the year-round default.
    Operators sometimes need to deviate for peak season — e.g. force Saturday
    changeovers in July/August even though the rest of the year permits any
    day. Each `ChangeOverRule` row expresses one such window.

    The 02-properties.md spec does not enumerate this model's columns; the
    shape below is the minimum needed to support the legacy `ChangeOverDays`
    behaviour without bringing back the lookup table. See reconciliation
    issue #(tbd) — refine before exposing in the API.
    """

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="changeover_rules",
    )
    day = models.CharField(
        max_length=8,
        choices=PrefilledChangeOverDay.choices,
    )
    starts_on = models.DateField()
    ends_on = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_on__gte=models.F("starts_on")),
                name="changeover_rule_ends_on_or_after_starts_on",
            ),
        ]
        ordering = ["property_id", "starts_on"]

    def __str__(self) -> str:
        return f"{self.day} {self.starts_on}..{self.ends_on} on property #{self.property_id}"
