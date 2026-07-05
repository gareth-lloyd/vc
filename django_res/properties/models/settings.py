from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel
from properties.enums import (
    AvailabilityDefault,
    PrefilledChangeOverDay,
    PriceBasis,
)


class PropertySettings(AuditedModel):
    """Per-property operational settings.

    Rows are materialised from the `PropertyDefaults` singleton at creation
    (`snapshot_defaults`); a NULL means *genuinely unset* — consumers apply a
    hardcoded final fallback where one exists (GAP-070).
    """

    property = models.OneToOneField(
        "properties.Property",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="settings",
    )
    availability_default = models.CharField(
        max_length=16,
        choices=AvailabilityDefault.choices,
        null=True,
        blank=True,
    )
    bookings_require_pre_approval = models.BooleanField(null=True, blank=True)
    requires_enquiry_first = models.BooleanField(null=True, blank=True)
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    check_in_time = models.TimeField(null=True, blank=True)
    check_out_time = models.TimeField(null=True, blank=True)
    changeover_day = models.CharField(
        max_length=8,
        choices=PrefilledChangeOverDay.choices,
        null=True,
        blank=True,
    )
    min_nights_rental = models.PositiveSmallIntegerField(null=True, blank=True)
    # `null=True` so the SettingsTab's `blankToNull`-on-submit can clear an
    # emptied note by sending `null`. Without it the whole Operational form
    # 400s ("This field may not be null.") whenever the note is empty.
    min_nights_rental_note = models.TextField(null=True, blank=True)
    prices_entered_as = models.CharField(
        max_length=8,
        choices=PriceBasis.choices,
        null=True,
        blank=True,
    )
    hold_duration_hours = models.PositiveSmallIntegerField(null=True, blank=True)
    # The owner's online (non-iCal) calendar webpage, surfaced to sales as a
    # quick link (GAP-034). Distinct from the secret iCal feed `url`
    # (`PropertyCalendarFeed`). `null=True` (not just `blank=True`) so the
    # SettingsTab's `blankToNull`-on-submit can clear it by sending `null`.
    calendar_url = models.URLField(max_length=500, null=True, blank=True)

    def __str__(self) -> str:
        return f"Settings for property #{self.property_id}"
