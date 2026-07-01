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

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError

from accounts.enums import OrgType
from accounts.models import Organisation, Person, User
from accounts.models.person import PersonEmail, PersonPhone
from core.console import render_table
from data_migration.legacy_db import legacy_cursor
from data_migration.loaders.integrations import SyncRecordZohoLoader
from data_migration.loaders.sentinels import CLIENT_LEGACY_PREFIX, UNKNOWN_CLIENT_LEGACY_ID
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
from reservations.models.quotation import Quotation, QuotationLine


@dataclass
class _Check:
    legacy_query: str
    model: type[Any]
    label: str
    expected_gap: int = 0
    # Optional override for the loaded-row count. Defaults to a bare
    # `model._default_manager.count()`; supply a callable when the model is
    # partitioned by a `legacy_id` prefix (GAP-045 D5-3: VillaContact and
    # VillaClientDetails both land in `accounts.Person`, so each check counts
    # only its own slice). The callable takes the model and returns the count.
    loaded_count: Callable[[type[Any]], int] | None = None


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
    _Check(
        "SELECT COUNT(*) FROM VillaContact WHERE DeletedAt IS NULL",
        Person,
        "Person (owner/agent)",
        # VillaContact owner/agent rows keep the bare legacy_id; GAP-045 D5-3
        # also lands VillaClientDetails customers in Person (keyed `client-{id}`),
        # so exclude every `client-` row here (the customer rows AND the
        # `unknown_client` sentinel) or they'd inflate the loaded count and turn
        # this check RED. The `client-` slice is checked separately below.
        loaded_count=lambda m: m._default_manager.exclude(
            legacy_id__startswith=CLIENT_LEGACY_PREFIX
        ).count(),
    ),
    _Check("SELECT COUNT(*) FROM VillaContactEmail", PersonEmail, "PersonEmail"),
    _Check("SELECT COUNT(*) FROM VillaContactTele", PersonPhone, "PersonPhone"),
    _Check(
        # GAP-046: every distinct (case/space-normalised) VillaContact.Company
        # becomes one Organisation(agency) via organisation_for_company_name, so
        # the loader actually created the orgs (catches a silent "zero orgs"
        # regression). SQL Server's default collation folds case + trailing
        # space but NOT internal whitespace, so the rare "Dune  Travel" vs
        # "Dune Travel" pair the helper merges shows as a small positive gap —
        # bump expected_gap at the first dry-run if so. Blank companies are
        # excluded both sides (helper returns None → no org).
        "SELECT COUNT(DISTINCT LTRIM(RTRIM(Company))) FROM VillaContact "
        "WHERE LTRIM(RTRIM(ISNULL(Company, ''))) <> ''",
        Organisation,
        "Organisation (agency)",
        loaded_count=lambda m: m._default_manager.filter(org_type=OrgType.AGENCY).count(),
    ),
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
        # BUG-013: RateRule now has two legacy sources — parent VillaSeasonRate
        # rows (→ simple / base-weekly fallback rules) AND child
        # VillaOccupencyPrice bands on occupancy-flagged parents (→ one band
        # rule each). Count both so the legacy side mirrors the loader's source
        # universe; children on non-occupancy parents are ignored by the loader
        # (`IsOccupationPrice` gate), so they're excluded here too.
        "SELECT "
        "(SELECT COUNT(*) FROM VillaSeasonRate "
        " WHERE DeletedAt IS NULL AND IsExTra <> 1) "
        "+ (SELECT COUNT(*) FROM VillaOccupencyPrice o "
        " JOIN VillaSeasonRate r ON r.ID = o.VillaSeasonRateId "
        " WHERE r.DeletedAt IS NULL AND r.IsExTra <> 1 AND r.IsOccupationPrice = 1)",
        RateRule,
        "RateRule",
        # PLACEHOLDER — recalibrate at the first post-BUG-013 cutover dry-run
        # against the live dump (no LEGACY_DATABASE_URL here to derive it). The
        # true gap now nets four moving parts against the two-part legacy count
        # above: MINUS synthetic base-weekly gap-fallback rules that have no
        # legacy row, MINUS the GAP-056 ragged-rule fragments the period
        # segmentation clones (a party-disjoint rule bisected by a sibling's date
        # boundary becomes >1 RateRule), PLUS dropped priceless / invalid-band /
        # overlap-covered rows and rows on the 67 unloaded seasons. The
        # fragment-inflation mechanism is unchanged, but there is no longer a
        # transitional `save()` shim or `backfill_plan_periods` pass: the
        # `RateRuleLoader._load_rows` builds each plan's disjoint `RatePeriod`
        # date axis directly via `segment_card_rules`. The old 3462+265 breakdown
        # (see CUTOVER.md "Rate rule overlap resolution") no longer holds as-is.
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
        Person,
        "Person (client)",
        # GAP-045 D5-3: VillaClientDetails now loads to Person directly (keyed
        # `client-{id}`), not Guest. Count only that slice, excluding the
        # `unknown_client` sentinel (minted only when a downstream row references
        # a skipped client — its presence must not move this count). The single
        # legacy row with neither FirstName nor LastName is still skipped
        # (expected_gap=1).
        expected_gap=1,
        loaded_count=lambda m: (
            m._default_manager.filter(legacy_id__startswith=CLIENT_LEGACY_PREFIX)
            .exclude(legacy_id=UNKNOWN_CLIENT_LEGACY_ID)
            .count()
        ),
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
            loaded_count = (
                check.loaded_count(check.model)
                if check.loaded_count is not None
                else check.model._default_manager.count()
            )
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
