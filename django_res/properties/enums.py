from __future__ import annotations

from django.db import models


class PropertyStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


# Allowed Property transitions, enforced by `PropertyLifecycleService` via
# `core.transitions`: activate from DRAFT/ARCHIVED, archive from DRAFT/ACTIVE,
# restore ARCHIVED → DRAFT.
PROPERTY_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    PropertyStatus.DRAFT.value: frozenset(
        {PropertyStatus.ACTIVE.value, PropertyStatus.ARCHIVED.value}
    ),
    PropertyStatus.ACTIVE.value: frozenset({PropertyStatus.ARCHIVED.value}),
    PropertyStatus.ARCHIVED.value: frozenset(
        {PropertyStatus.ACTIVE.value, PropertyStatus.DRAFT.value}
    ),
}


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
    """Customer-facing vs. agent-net price basis.

    The sole definition (SMELL-021). Two consumers with distinct authority:
    `RatePlan.price_basis` is what the pricing engine branches on (BUG-009);
    `PropertySettings.prices_entered_as` is only the entry-form pre-fill for
    new plans (GAP-035).
    """

    GROSS = "gross", "Gross"
    NET = "net", "Net"


class ImageKind(models.TextChoices):
    HERO = "hero", "Hero"
    INTERIOR = "interior", "Interior"
    EXTERIOR = "exterior", "Exterior"
    GALLERY = "gallery", "Gallery"
    FLOOR_PLAN = "floor_plan", "Floor plan"


class RoomPlacement(models.TextChoices):
    """Which building/structure a room is in ("" = unknown)."""

    MAIN_HOUSE = "main_house", "Main house"
    GUEST_HOUSE = "guest_house", "Guest house"
    POOL_HOUSE = "pool_house", "Pool house"
    ANNEX = "annex", "Annexe"
    COTTAGE = "cottage", "Cottage"
    BUNGALOW = "bungalow", "Bungalow"
    STUDIO = "studio", "Studio"
    OTHER = "other", "Other"


class RoomFloor(models.TextChoices):
    """Fixed floor ladder ("" = unknown). Rare oddities (mezzanine, basement)
    stay blank with the raw legacy string preserved in `placement_note`."""

    LOWER_GROUND = "lower_ground", "Lower ground"
    GROUND = "ground", "Ground"
    FIRST = "first", "First"
    SECOND = "second", "Second"
    THIRD_PLUS = "third_plus", "Third or above"


class EnsuiteType(models.TextChoices):
    """Refines `Room.is_ensuite` when the facility kind is known ("" = unknown)."""

    SHOWER = "shower", "Shower"
    BATH = "bath", "Bath"
    BOTH = "both", "Bath & shower"


class BedSize(models.TextChoices):
    """Size of a `RoomBeds.double` bed ("" = unspecified). Size only ever
    qualifies a double (King/Super-king/Emperor); twins/singles are unqualified.
    A plain double with a blank size reads simply as "Double" (GAP-066)."""

    KING = "king", "King"
    SUPER_KING = "super_king", "Super-king"
    EMPEROR = "emperor", "Emperor"


class RoomAccess(models.TextChoices):
    INSIDE = "inside", "Inside access"
    OUTSIDE = "outside", "Separate outside access"


class DescriptionSection(models.TextChoices):
    """Long-form copy blocks on a property, one row per section.

    `INTERNAL_NOTES` is staff-only: the SPA groups it apart from the website
    copy and property duplication drops it
    (`PropertyLifecycleService.duplicate`). There is no per-row visibility
    column — the whole properties API is staff-gated, so the split is a UI
    affordance, not access control.

    The rest are guest-facing, except `HOUSE_RULES`.
    `HOUSE_RULES` is never shown online: it rides into the **booking
    contract**, snapshotted onto `Booking.house_rules_snapshot` at
    confirmation and rendered from there (GAP-094), so later edits here cannot
    rewrite a contract a guest already holds. It reaches no public payload,
    and five sentinel leak guards pin that (`test_zoho_villa.py` here, plus
    reservations' `test_zoho_booking.py`, `test_api_wordpress_enquiries.py`,
    `test_stay_options.py` and `test_owner_bookings.py`). Legacy did select
    `QuotationArgs.HouseRules` for the quotation but never output it — the
    quotation is not where these go.

    GAP-090 rebuilt the website set to the legacy block shape: the public site
    renders each block as a short **sub** (lead-in) plus a longer **para**, and
    legacy stores them as the column pairs `WebDesc1/2`, `Interior1/2`,
    `Exterior1/2`, `Location1/2` on `VillaPropertyImagesDescription` (the
    2026-07-20 Nick recording, legacy screen at [01:48]). The loader used to
    fuse each pair with a blank line, so `WEB_DESCRIPTION` and `LOCATION` were
    unsplittable; those are gone, along with `FURTHER_INFO` — its legacy
    source is `VillaMaster.Notes`, which the same recording settles as staff
    copy ("we can get rid of further info, just make it internal notes"), so
    it loads into `INTERNAL_NOTES` now. Migration 0010 remapped the loaded
    rows (`web_description` → `WEB_DES_1`, `location` → `LOCATION_SUB`,
    `further_info` → `INTERNAL_NOTES`); those bodies stay fused until the
    loader re-run in `data_migration/CUTOVER.md` §6i rewrites each half into
    its own section. `OVERVIEW` (legacy `VillaMaster.OverView`, a different
    column on a different screen) was retired on 2026-09-22: only 8 ResProd
    villas carried it, 6 of which also have `WebDesc1`, so migration 0011
    dropped those rows as an expected loss rather than remap them —
    `WEB_DES_1` is written from `WebDesc1` only, never from `OverView`.

    `OTHER_INFORMATION` (GAP-091) is the prose half of the legacy Features
    screen's "Other information" — it lives on the Features tab beside the
    other-information tags (legacy `VillaMaster.FeatureDescription`), not on
    the Descriptions panel. `ROOMS` is the single property-level blurb legacy
    shows under the bedrooms (`VillaMaster.RoomDescription`); the enum member
    landed with GAP-091, rendering it (and retiring the per-room field) is
    GAP-092. The retired `villa_info` fused both; migration 0007 renamed its
    rows to `other_information`.
    """

    HOUSE_RULES = "house_rules", "House rules"
    WEB_DES_1 = "web_des_1", "Web des 1"
    WEB_DES_2 = "web_des_2", "Web des 2"
    INTERIOR_SUB = "interior_sub", "Interior sub"
    INTERIOR_PARA = "interior_para", "Interior para"
    EXTERIOR_SUB = "exterior_sub", "Exterior sub"
    EXTERIOR_PARA = "exterior_para", "Exterior para"
    LOCATION_SUB = "location_sub", "Location sub"
    LOCATION_PARA = "location_para", "Location para"
    INTERNAL_NOTES = "internal_notes", "Internal notes"
    OTHER_INFORMATION = "other_information", "Other information"
    ROOMS = "rooms", "Rooms"


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
