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
    _Check(
        "SELECT COUNT(*) FROM VillaCountry",
        Country,
        "Country (legacy)",
        # Negative gap: loaded > legacy. Migration properties.0009 pre-seeds
        # 249 canonical ISO-3166 countries (legacy_id NULL); the 23 legacy
        # VillaCountry rows are matched onto that seed by iso2 rather than
        # adding to it. Plus the unknown_country sentinel. The seeded table
        # dwarfs the 23 legacy rows, so the gap is structurally negative.
        expected_gap=-228,
    ),
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
        expected_gap=-1,  # unknown_group sentinel row (no legacy origin).
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
    _Check(
        "SELECT COUNT(*) FROM VillaRooms",
        Room,
        "Room",
        # Rooms whose VillaId points at a property that wasn't loaded
        # (soft-deleted or empty-Name VillaMaster) have no parent to attach to.
        expected_gap=307,
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaPropertyImages",
        PropertyImage,
        "PropertyImage",
        # Images for an unloaded parent property, or rows with an empty filename.
        expected_gap=806,
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaNearBy",
        PropertyNearbyPlace,
        "PropertyNearbyPlace",
        # Parent property unresolved, place type unresolved, or empty name.
        expected_gap=77,
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaSeason WHERE DeletedAt IS NULL",
        RatePlan,
        "RatePlan",
        # Seasons whose VillaId doesn't resolve, or with no resolvable currency
        # (none on the season's rates and none configured on the property/group).
        expected_gap=67,
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaSeasonRate WHERE DeletedAt IS NULL AND IsExTra <> 1",
        RateRule,
        "RateRule",
        # 3462 = the pre-resolver gap (priceless rows — unusable in legacy
        # too — plus rows on the 67 unloaded seasons), + 265 rows dropped by
        # load-time overlap resolution (fully covered by a winning row; 389
        # total drops, but 124 sit on unloaded seasons and were already in
        # the 3462). See CUTOVER.md "Rate rule overlap resolution".
        expected_gap=3727,
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaContactMapping",
        PropertyContactAssignment,
        "PropertyContactAssignment",
        expected_gap=1,  # composite legacy_id collapse.
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaClientDetails",
        Guest,
        "Guest",
        expected_gap=1,  # one legacy row with neither FirstName nor LastName.
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaEnquire",
        Enquiry,
        "Enquiry",
        # Negative gap: loaded > legacy. Synthesised enquiries created to
        # satisfy the now-mandatory Quotation.enquiry FK — for booking-synth
        # quotations (BookingLoader.ensure_enquiry) and legacy quotations that
        # carried no enquiry of their own.
        expected_gap=-8,
    ),
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
        # Negative gap: BookingLoader synthesises a hidden DRAFT quotation per
        # legacy booking that has no real quotation to satisfy the PROTECT FK.
        expected_gap=-3,
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaQuotationDetails",
        QuotationLine,
        "QuotationLine (legacy + booking-synth)",
        expected_gap=-2,  # lines on the booking-synth quotations above.
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
        """Per Zoho source: backfilled SyncRecord vs the legacy rows that need one.

        The continuity question is "does every *loaded* row that carried a
        legacy ZohoId now have a SyncRecord?" — because only a loaded row has a
        Django object the first post-cutover push could duplicate against. So we
        compare the count of SyncRecords against `loaded`: the legacy rows with a
        non-blank ZohoId whose `legacy_id` actually resolves to an imported row.

        This deliberately resolves through `legacy_id__in` rather than re-deriving
        the legacy count with a per-table WHERE: a ZohoId on a row the domain
        loader dropped (soft-deleted `DeletedAt`, empty `Name`, an unresolvable
        FK) has no push target and is *not* a continuity failure — counting it
        would be a false blocker. `legacy ext id` is still shown raw so the
        operator can see how many ZohoId rows were not imported.

        `external_id__gt=""` mirrors the model's partial-unique condition and the
        loader's own non-blank guard: a transmitted-but-not-pushed record (e.g.
        `quotation_transmission` mints a PENDING SyncRecord with a blank
        external_id) must not be counted as a captured external id, or it would
        mask a genuinely missing one.

        Limitation: this compares counts, not values. A full `loadlegacy --all`
        refreshes every external_id (`update_or_create`), but a value that
        drifted on a delta-only `--since` load whose `UpdatedAt` did not advance
        would not be caught here.
        """
        rows: list[tuple[str, int, int, int, int, str]] = []
        blockers: list[str] = []
        for spec in SyncRecordZohoLoader.SPECS:
            cursor.execute(
                f"SELECT Id FROM {spec.table} "
                f"WHERE ZohoId IS NOT NULL AND LTRIM(RTRIM(ZohoId)) <> ''"
            )
            legacy_ids = [str(r[0]) for r in cursor.fetchall()]
            legacy_ext = len(legacy_ids)
            loaded = (
                spec.model._default_manager.filter(legacy_id__in=legacy_ids).count()
                if legacy_ids
                else 0
            )
            sync_records = SyncRecord.objects.filter(
                provider=SyncProvider.ZOHO_CRM,
                content_type=ContentType.objects.get_for_model(spec.model),
                external_id__gt="",
            ).count()
            gap = loaded - sync_records
            ok = gap == 0
            if not ok:
                blockers.append(
                    f"{spec.table}.ZohoId: continuity gap {gap} "
                    f"({loaded} loaded with a ZohoId vs {sync_records} SyncRecord(s))"
                )
            rows.append(
                (
                    f"{spec.table}.ZohoId",
                    legacy_ext,
                    loaded,
                    sync_records,
                    gap,
                    "OK" if ok else "BLOCKER",
                )
            )

        header = ("zoho source", "legacy ext id", "loaded", "sync records", "gap", "status")
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
