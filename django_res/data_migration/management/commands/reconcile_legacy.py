"""Compare legacy row counts against loaded Django row counts.

Prints a table:

    table                  legacy   loaded   gap    %
    VillaMaster            441      441      0      100
    VillaPropertyImages    13089    13089    0      100
    ...

The list of (legacy_table_or_query, django_model) pairs is explicit so
gaps mirror loader scope (e.g. VillaMaster's `WHERE DeletedAt IS NULL` is
mirrored here). When `expected_gap` is non-zero, it documents a known loss
(e.g. VillaFinance: ~676 parent-child override rows aren't migrated).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.management.base import BaseCommand

from accounts.models import Contact, User
from accounts.models.contact import ContactEmail, ContactPhone
from data_migration.legacy_db import legacy_cursor
from payments.models.payment import Payment
from pricing.models.currency import Currency
from pricing.models.rate import RatePlan, RateRule
from properties.models.contacts import PropertyContactAssignment
from properties.models.features import (
    Collection,
    CollectionMembership,
    Feature,
    FeatureCategory,
)
from properties.models.finance import PropertyFinance
from properties.models.geo import Country, NearbyPlaceType, PropertyNearbyPlace, Region
from properties.models.images import PropertyImage
from properties.models.property import Property, PropertyCategory, PropertyGroup
from properties.models.rooms import Room
from reservations.models.booking import Booking
from reservations.models.enquiry import Enquiry
from reservations.models.guest import Guest
from reservations.models.quotation import Quotation, QuotationLine


@dataclass
class _Check:
    legacy_query: str
    model: type[Any]
    label: str
    expected_gap: int = 0
    extra_filter: dict[str, Any] | None = None


_CHECKS: list[_Check] = [
    _Check("SELECT COUNT(*) FROM VillaCountry", Country, "Country (legacy)"),
    _Check("SELECT COUNT(*) FROM VillaRegion", Region, "Region"),
    _Check("SELECT COUNT(*) FROM VillaCurrency", Currency, "Currency"),
    _Check("SELECT COUNT(*) FROM VillaPropertyCategory", PropertyCategory, "PropertyCategory"),
    _Check("SELECT COUNT(*) FROM VillaNearByLocationType", NearbyPlaceType, "NearbyPlaceType"),
    _Check("SELECT COUNT(*) FROM VillaFeaturesCategory", FeatureCategory, "FeatureCategory"),
    _Check(
        "SELECT COUNT(*) FROM VillaFeatures WHERE DeletedAt IS NULL",
        Feature,
        "Feature",
    ),
    _Check("SELECT COUNT(*) FROM UserMaster WHERE DeletedAt IS NULL", User, "User"),
    _Check("SELECT COUNT(*) FROM VillaContact WHERE DeletedAt IS NULL", Contact, "Contact"),
    _Check("SELECT COUNT(*) FROM VillaContactEmail", ContactEmail, "ContactEmail"),
    _Check("SELECT COUNT(*) FROM VillaContactTele", ContactPhone, "ContactPhone"),
    _Check(
        "SELECT COUNT(*) FROM VillaGroup WHERE DeletedAt IS NULL",
        PropertyGroup,
        "PropertyGroup",
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaMaster WHERE DeletedAt IS NULL",
        Property,
        "Property",
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaCollection WHERE DeletedAt IS NULL",
        Collection,
        "Collection",
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaCollectionsMappings",
        CollectionMembership,
        "CollectionMembership",
        expected_gap=308,  # legacy duplicates (multiple rows per same pair).
    ),
    _Check("SELECT COUNT(*) FROM VillaRooms", Room, "Room"),
    _Check("SELECT COUNT(*) FROM VillaPropertyImages", PropertyImage, "PropertyImage"),
    _Check("SELECT COUNT(*) FROM VillaNearBy", PropertyNearbyPlace, "PropertyNearbyPlace"),
    _Check(
        "SELECT COUNT(*) FROM VillaSeason WHERE DeletedAt IS NULL",
        RatePlan,
        "RatePlan",
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaSeasonRate WHERE DeletedAt IS NULL AND IsExTra <> 1",
        RateRule,
        "RateRule",
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaContactMapping",
        PropertyContactAssignment,
        "PropertyContactAssignment",
    ),
    _Check("SELECT COUNT(*) FROM VillaClientDetails", Guest, "Guest"),
    _Check("SELECT COUNT(*) FROM VillaEnquire", Enquiry, "Enquiry"),
    _Check(
        "SELECT COUNT(*) FROM VillaFinance WHERE VillaId IS NOT NULL",
        PropertyFinance,
        "PropertyFinance",
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaQuotationMaster WHERE DeletedAt IS NULL",
        Quotation,
        "Quotation (legacy + booking-synth)",
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaQuotationDetails",
        QuotationLine,
        "QuotationLine (legacy + booking-synth)",
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaBooking WHERE DeletedAt IS NULL",
        Booking,
        "Booking",
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaPaymentDetails d JOIN VillaPayment p ON p.Id = d.PaymentId",
        Payment,
        "Payment",
    ),
]


class Command(BaseCommand):
    help = "Compare legacy row counts vs loaded Django row counts."

    def handle(self, *args: Any, **options: Any) -> None:
        rows: list[tuple[str, int, int, int, str]] = []
        with legacy_cursor() as cursor:
            for check in _CHECKS:
                cursor.execute(check.legacy_query)
                legacy_count = int(cursor.fetchone()[0])
                loaded_count = check.model._default_manager.count()
                gap = legacy_count - loaded_count
                pct = (loaded_count / legacy_count * 100) if legacy_count else 100.0
                rows.append(
                    (
                        check.label,
                        legacy_count,
                        loaded_count,
                        gap,
                        f"{pct:5.1f}",
                    )
                )

        header = ("table", "legacy", "loaded", "gap", "%")
        formatted: list[tuple[str, ...]] = [header]
        for label, legacy_count, loaded_count, gap, pct in rows:
            formatted.append((label, str(legacy_count), str(loaded_count), str(gap), pct))

        widths = [max(len(c) for c in col) for col in zip(*formatted, strict=True)]
        for i, row in enumerate(formatted):
            self.stdout.write("  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)))
            if i == 0:
                self.stdout.write("  ".join("-" * w for w in widths))
