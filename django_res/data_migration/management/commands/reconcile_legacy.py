"""Compare legacy row counts against loaded Django row counts.

Prints a table and exits non-zero if any row's gap doesn't match its
documented expectation:

    table                  legacy   loaded   gap    expected   status
    VillaMaster            441      440      1      1          OK
    VillaPropertyImages    13089    13089    0      0          OK
    CollectionMembership   1234     926      308    308        OK
    ...

The list of (legacy_table_or_query, django_model) pairs is explicit so
gaps mirror loader scope (e.g. VillaMaster's `WHERE DeletedAt IS NULL` is
mirrored here). `expected_gap` is the documented, accepted loss for that
table (e.g. VillaFinance override rows with no schema home); this module is
the single source of truth for those numbers — `CUTOVER.md` points here
rather than duplicating them.

A row whose `gap != expected_gap` is a **BLOCKER**: an unexplained extra
loss, or fewer/more rows than the documented carve-out predicts. Any
blocker makes the command exit non-zero, so the cutover playbook can gate
on it mechanically instead of a manual cross-reference against a markdown
table. The `expected_gap` values are calibrated against the reference dump;
the first cutover dry-run is where they are confirmed (or adjusted here)
against live counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Contact, User
from accounts.models.contact import ContactEmail, ContactPhone
from core.console import render_table
from data_migration.legacy_db import legacy_cursor
from data_migration.loaders.integrations import SyncRecordZohoLoader
from integrations.enums import SyncProvider
from integrations.models import SyncRecord
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


_CHECKS: list[_Check] = [
    _Check("SELECT COUNT(*) FROM VillaCountry", Country, "Country (legacy)"),
    _Check("SELECT COUNT(*) FROM VillaRegion", Region, "Region"),
    _Check(
        "SELECT COUNT(*) FROM VillaCurrency",
        Currency,
        "Currency",
        expected_gap=4,  # junk rows (HTFG/RUPEE/RS) with zero FK references.
    ),
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
        expected_gap=1,  # one row with empty Name.
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
        expected_gap=3462,  # rows with no price (all-NULL, IsPOA=0) — unusable in legacy too.
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaContactMapping",
        PropertyContactAssignment,
        "PropertyContactAssignment",
        expected_gap=1,  # composite legacy_id collapse.
    ),
    _Check("SELECT COUNT(*) FROM VillaClientDetails", Guest, "Guest"),
    _Check("SELECT COUNT(*) FROM VillaEnquire", Enquiry, "Enquiry"),
    _Check(
        "SELECT COUNT(*) FROM VillaFinance WHERE VillaId IS NOT NULL",
        PropertyFinance,
        "PropertyFinance",
        # 413 contact-default rows mirror onto GroupFinance (no 1:1 mapping);
        # 676 parent-child override rows have no schema equivalent.
        expected_gap=1236,
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

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--integrations",
            action="store_true",
            help=(
                "Also check external-ID continuity: legacy Zoho ids vs "
                "backfilled SyncRecord rows (a blocker if any are missing), "
                "plus an informational WordPress surface."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        blockers: list[str] = []
        with legacy_cursor() as cursor:
            blockers += self._row_count_section(cursor)
            if options["integrations"]:
                blockers += self._zoho_continuity_section(cursor)
                self._wordpress_info_section(cursor)

        if blockers:
            raise CommandError(
                f"{len(blockers)} reconcile blocker(s) — cutover must not proceed:\n  "
                + "\n  ".join(blockers)
            )

    def _row_count_section(self, cursor: Any) -> list[str]:
        """Main legacy-vs-loaded row-count table. Returns blocker messages."""
        rows: list[tuple[str, int, int, int, int, str]] = []
        blockers: list[str] = []
        for check in _CHECKS:
            cursor.execute(check.legacy_query)
            legacy_count = int(cursor.fetchone()[0])
            loaded_count = check.model._default_manager.count()
            gap = legacy_count - loaded_count
            ok = gap == check.expected_gap
            if not ok:
                blockers.append(f"{check.label}: gap {gap} != expected {check.expected_gap}")
            rows.append(
                (
                    check.label,
                    legacy_count,
                    loaded_count,
                    gap,
                    check.expected_gap,
                    "OK" if ok else "BLOCKER",
                )
            )

        header = ("table", "legacy", "loaded", "gap", "expected", "status")
        self.stdout.write(render_table(header, rows))
        return blockers

    def _zoho_continuity_section(self, cursor: Any) -> list[str]:
        """Per Zoho source: non-blank legacy ZohoId vs backfilled SyncRecord.

        A gap means a legacy external id has no SyncRecord — the first
        post-cutover push would mint a duplicate Zoho record, so it blocks.
        """
        rows: list[tuple[str, int, int, int, str]] = []
        blockers: list[str] = []
        for spec in SyncRecordZohoLoader.SPECS:
            cursor.execute(
                f"SELECT COUNT(*) FROM {spec.table} "
                f"WHERE ZohoId IS NOT NULL AND LTRIM(RTRIM(ZohoId)) <> ''"
            )
            legacy_ext = int(cursor.fetchone()[0])
            sync_records = SyncRecord.objects.filter(
                provider=SyncProvider.ZOHO_CRM,
                content_type=ContentType.objects.get_for_model(spec.model),
            ).count()
            gap = legacy_ext - sync_records
            ok = gap == 0
            if not ok:
                blockers.append(f"{spec.table}.ZohoId: {gap} external id(s) without a SyncRecord")
            rows.append(
                (
                    f"{spec.table}.ZohoId",
                    legacy_ext,
                    sync_records,
                    gap,
                    "OK" if ok else "BLOCKER",
                )
            )

        header = ("zoho source", "legacy ext id", "sync records", "gap", "status")
        self.stdout.write("\n\nZoho external-ID continuity:\n")
        self.stdout.write(render_table(header, rows))
        return blockers

    def _wordpress_info_section(self, cursor: Any) -> None:
        """Informational WordPress surface — never blocks.

        The WordPress SyncRecord backfill is not built yet (it needs a
        `provider_instance` model change — see the audit), so this reports the
        legacy WP external-id volume an operator must account for rather than
        asserting continuity and printing a false "all clear".
        """
        rows: list[tuple[str, str, str]] = []

        def _count(label: str, query: str) -> None:
            try:
                cursor.execute(query)
                rows.append((label, str(int(cursor.fetchone()[0])), "INFO"))
            except Exception as exc:
                # Defensive: a dry-run dump may predate VillaSyncDetail. This
                # section is informational, so degrade to "n/a" rather than
                # aborting the whole reconcile.
                rows.append((label, f"n/a ({type(exc).__name__})", "INFO"))

        _count(
            "VillaBooking.BookingUrl",
            "SELECT COUNT(*) FROM VillaBooking "
            "WHERE BookingUrl IS NOT NULL AND LTRIM(RTRIM(BookingUrl)) <> ''",
        )
        _count("VillaSyncDetail (rows)", "SELECT COUNT(*) FROM VillaSyncDetail")
        _count(
            "VillaSyncDetail (sites)",
            "SELECT COUNT(DISTINCT SiteId) FROM VillaSyncDetail",
        )

        header = ("wordpress source", "legacy count", "status")
        self.stdout.write("\n\nWordPress external-ID surface (informational — loader not built):\n")
        self.stdout.write(render_table(header, rows))
