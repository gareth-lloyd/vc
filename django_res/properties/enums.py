from __future__ import annotations

from django.db import models


class PropertyStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class PropertyChannel(models.TextChoices):
    DIRECT = "direct", "Direct"
    AGENT = "agent", "Agent"
    WHITE_LABEL = "white_label", "White label"
    INTERNAL = "internal", "Internal"


class AvailabilityDefault(models.TextChoices):
    AVAILABLE = "available", "Available"
    UNAVAILABLE = "unavailable", "Unavailable"
    ON_REQUEST = "on_request", "On request"


class PrefilledChangeOverDay(models.TextChoices):
    MON = "mon", "Monday"
    TUE = "tue", "Tuesday"
    WED = "wed", "Wednesday"
    THU = "thu", "Thursday"
    FRI = "fri", "Friday"
    SAT = "sat", "Saturday"
    SUN = "sun", "Sunday"
    ANY = "any", "Any day"


class PriceBasis(models.TextChoices):
    GROSS = "gross", "Gross"
    NET = "net", "Net"


class ImageKind(models.TextChoices):
    HERO = "hero", "Hero"
    INTERIOR = "interior", "Interior"
    EXTERIOR = "exterior", "Exterior"
    GALLERY = "gallery", "Gallery"
    FLOOR_PLAN = "floor_plan", "Floor plan"


class RoomPlacement(models.TextChoices):
    MAIN_HOUSE = "main_house", "Main house"
    GUEST_HOUSE = "guest_house", "Guest house"
    POOL_HOUSE = "pool_house", "Pool house"
    ANNEX = "annex", "Annex"
    OTHER = "other", "Other"


class DescriptionSection(models.TextChoices):
    OVERVIEW = "overview", "Overview"
    HOUSE_RULES = "house_rules", "House rules"
    VILLA_INFO = "villa_info", "Villa info"
    FURTHER_INFO = "further_info", "Further info"


class FeatureServiceType(models.TextChoices):
    AMENITY = "amenity", "Amenity"
    INCLUDED_SERVICE = "included_service", "Included service"
    PAID_ADDON = "paid_addon", "Paid add-on"


class CommissionCalcType(models.TextChoices):
    PERCENT = "percent", "Percent"
    FIXED = "fixed", "Fixed"


class DepositCalcType(models.TextChoices):
    PERCENT = "percent", "Percent"
    FIXED = "fixed", "Fixed"


class SecurityDepositCalcType(models.TextChoices):
    PERCENT = "percent", "Percent"
    FIXED = "fixed", "Fixed"


class SecurityDepositPaymentMethod(models.TextChoices):
    CARD_HOLD = "card_hold", "Card hold"
    CARD_CHARGE = "card_charge", "Card charge"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"


# Note on contact roles: the role used by `PropertyContactAssignment` is the
# `accounts.ContactRole` TextChoices. No properties-local enum is defined; the
# assignment model references the accounts enum directly. The user-supplied
# enum list mentioned a `ContactRoleStartShape` placeholder for forward-compat,
# but the spec (`02-properties.md`) makes no use of it, so it is intentionally
# omitted to avoid a dead symbol.
