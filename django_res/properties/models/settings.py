from __future__ import annotations

from typing import Any

from django.db import models

from core.models.base import AuditedModel
from properties.enums import (
    AvailabilityDefault,
    PrefilledChangeOverDay,
    PriceBasis,
)

# Field names that are inheritable from the group when null on the property.
_INHERITABLE_FIELDS = frozenset(
    {
        "availability_default",
        "bookings_require_pre_approval",
        "requires_enquiry_first",
        "currency",
        "check_in_time",
        "check_out_time",
        "changeover_day",
        "min_nights_rental",
        "min_nights_rental_note",
        "prices_entered_as",
        "hold_duration_hours",
    }
)


class PropertySettings(AuditedModel):
    """Per-property operational settings.

    Every inheritable field is nullable; `None` means *inherit from the group*.
    Use `effective(field)` to resolve the inheritance chain.
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
    min_nights_rental_note = models.TextField(blank=True)
    prices_entered_as = models.CharField(
        max_length=8,
        choices=PriceBasis.choices,
        null=True,
        blank=True,
    )
    hold_duration_hours = models.PositiveSmallIntegerField(null=True, blank=True)
    # The owner's online (non-iCal) calendar webpage, surfaced to sales as a
    # quick link (GAP-034). Distinct from the secret iCal feed `url`
    # (`PropertyCalendarFeed`). Per-villa, never inherited, so it is NOT in
    # `_INHERITABLE_FIELDS` nor mirrored on `GroupSettings`. `null=True` (not
    # just `blank=True`) so the SettingsTab's `blankToNull`-on-submit can clear
    # it by sending `null`.
    calendar_url = models.URLField(max_length=500, null=True, blank=True)

    def __str__(self) -> str:
        return f"Settings for property #{self.property_id}"

    def effective(self, attr: str) -> Any:
        """Resolve `attr` with group-level fallback when the property value is null.

        Raises `AttributeError` if `attr` is not an inheritable settings field.
        """
        if attr not in _INHERITABLE_FIELDS:
            raise AttributeError(f"{attr!r} is not an inheritable settings field")
        own = getattr(self, attr)
        if own is not None and own != "":
            return own
        return getattr(self.property.group.settings, attr)


class GroupSettings(AuditedModel):
    """Per-group fallback settings. Every inheritable field is non-null with a default."""

    group = models.OneToOneField(
        "properties.PropertyGroup",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="settings",
    )
    availability_default = models.CharField(
        max_length=16,
        choices=AvailabilityDefault.choices,
        default=AvailabilityDefault.AVAILABLE,
    )
    bookings_require_pre_approval = models.BooleanField(default=False)
    requires_enquiry_first = models.BooleanField(default=False)
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
        default=PrefilledChangeOverDay.ANY,
    )
    min_nights_rental = models.PositiveSmallIntegerField(default=1)
    min_nights_rental_note = models.TextField(blank=True)
    prices_entered_as = models.CharField(
        max_length=8,
        choices=PriceBasis.choices,
        default=PriceBasis.GROSS,
    )
    hold_duration_hours = models.PositiveSmallIntegerField(default=48)

    def __str__(self) -> str:
        return f"Settings for group #{self.group_id}"
