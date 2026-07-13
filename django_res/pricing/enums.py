"""TextChoices enumerations for the pricing app."""

from __future__ import annotations

from django.db import models


class RuleKind(models.TextChoices):
    """Discount rule kind — controls when/how a discount auto-applies."""

    LENGTH_OF_STAY = "length_of_stay", "Length of stay"
    EARLY_BIRD = "early_bird", "Early bird"
    LAST_MINUTE = "last_minute", "Last minute"
    REPEAT_GUEST = "repeat_guest", "Repeat guest"
    PROMO_CODE = "promo_code", "Promo code"


class DiscountKind(models.TextChoices):
    """Whether the discount amount is a percentage or a fixed currency amount."""

    PERCENT = "percent", "Percent"
    FIXED = "fixed", "Fixed"


class ExtraKind(models.TextChoices):
    """Catalogue of named, property-scoped charges added at quote time."""

    CLEANING = "cleaning", "Cleaning"
    PET_FEE = "pet_fee", "Pet fee"
    HEATING = "heating", "Heating"
    LINEN = "linen", "Linen"
    EXTRA_BED = "extra_bed", "Extra bed"
    SERVICE_FEE = "service_fee", "Service fee"
    RESORT_FEE = "resort_fee", "Resort fee"
    OTHER = "other", "Other"


class ExtraCalc(models.TextChoices):
    """How an Extra's `amount` is converted to a per-quote `computed_amount`."""

    FIXED_PER_STAY = "fixed_per_stay", "Fixed per stay"
    FIXED_PER_NIGHT = "fixed_per_night", "Fixed per night"
    FIXED_PER_PERSON = "fixed_per_person", "Fixed per person"
    FIXED_PER_PERSON_PER_NIGHT = (
        "fixed_per_person_per_night",
        "Fixed per person per night",
    )
    PERCENT_OF_SUBTOTAL = "percent_of_subtotal", "Percent of subtotal"
