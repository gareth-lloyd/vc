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
from data_migration.loaders.availability import AVAILABILITY_LEGACY_PREFIX
from data_migration.loaders.integrations import SyncRecordZohoLoader, zoho_id_column_exists
from data_migration.loaders.sentinels import CLIENT_LEGACY_PREFIX, UNKNOWN_CLIENT_LEGACY_ID
from integrations.enums import SyncProvider
from integrations.models import SyncRecord
from payments.models.payment import Payment
from pricing.models.currency import Currency
from pricing.models.rate import RateBand, RatePlan
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
from properties.models.property import Property, PropertyCategory
from properties.models.rooms import Room
from reservations.models.booking import Booking, BookingHold
from reservations.models.charge_item import BookingChargeItem
from reservations.models.enquiry import Enquiry
from reservations.models.preferences import GuestPreference, GuestPreferenceType
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
    _Check(
        "SELECT COUNT(*) FROM VillaContactEmail",
        PersonEmail,
        "PersonEmail",
        # GAP-045: ClientLoader also reconciles VillaClientDetails email
        # columns onto the `client-` Person slice, but the legacy side here
        # counts only VillaContactEmail — exclude client-owned channels
        # (mirrors the "Person (owner/agent)" slice split above) or every
        # client email shows as a negative gap (dry-run 1: 30 of them).
        loaded_count=lambda m: m._default_manager.exclude(
            contact__legacy_id__startswith=CLIENT_LEGACY_PREFIX
        ).count(),
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaContactTele",
        PersonPhone,
        "PersonPhone",
        # Same client-slice exclusion as PersonEmail above.
        loaded_count=lambda m: m._default_manager.exclude(
            contact__legacy_id__startswith=CLIENT_LEGACY_PREFIX
        ).count(),
    ),
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
        "SELECT COUNT(*) FROM VillaRooms WHERE PlacementId IS NOT NULL",
        Room,
        "Room placement (GAP-065)",
        # No-loss gate: every legacy room with a placement must land with the
        # raw string preserved in `placement_note`. PLACEHOLDER — recalibrate
        # at the first cutover dry-run (BUG-013 precedent). The gap has two
        # legitimate causes to apportion then: (a) rooms whose parent property
        # wasn't loaded (the 307 slice above, restricted to rows with a
        # PlacementId); (b) dangling PlacementId → NULL/blank
        # VillaRoomsPlacement.Name (the LEFT JOIN preserves the room but the
        # note is honestly empty).
        # `placement_note` is API-writable, so count only the legacy slice —
        # a staff-entered note during the cutover window must not shift the
        # gap (the BookingChargeItem precedent below).
        expected_gap=0,
        loaded_count=lambda m: (
            m._default_manager.exclude(placement_note="").filter(legacy_id__isnull=False).count()
        ),
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
        # (none on the season's rates and none configured on the property).
        expected_gap=67,
    ),
    _Check(
        # BUG-013: RateBand now has two legacy sources — parent VillaSeasonRate
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
        RateBand,
        "RateBand",
        # Calibrated 2026-07-05 against the 24-Apr-2025 prod dump (DRYRUN_LOG
        # run 1). Legacy 7333 = 7082 VillaSeasonRate parents + 251 occupancy
        # children; loaded 3528 = 3265 simple + 27 #seg fragments + 235 occ-*
        # bands + 1 occ-fb-* gap fallback. Itemised (balances exactly, zero
        # residual):
        #   +  108  occupancy-banded parents replaced by their band expansion
        #   + 2477  priceless non-POA rows (2476 simple + 1 fallback with a
        #           NULL parent base price)
        #   +  985  rows on seasons with no RatePlan (654 on deleted/dangling
        #           seasons + 331 on 59 of the 67 unloaded live seasons)
        #   +  106  synthetic gap fallbacks emptied by capacity (bands
        #           already cover 1..cap)
        #   +  264  flattener-shadowed sources (248 simple + 16 duplicate occ
        #           bands at identical price — no distinct price lost)
        #   -  108  synthetic occ-fb-* fallback rows added by expansion
        #   -   27  #seg fragments added by the flattener
        # Junk dates / invalid occ children / resolver dedupe: all 0 on this
        # dump. Recalibrate on a newer dump — the mix (especially priceless
        # rows and unloaded seasons) moves with the data, not the code.
        expected_gap=3805,
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
        # 1236 is a PLACEHOLDER to recalibrate at the first post-GAP-070
        # dry-run (BUG-013 precedent). It was exact while the loaded side
        # matched the legacy `VillaId IS NOT NULL` universe 1:1: the 1236 =
        # 413 contact-default template rows (VillaId NULL, no per-villa
        # equivalent) + 676 parent-child override rows (no schema home) +
        # skips. The owner-contact fallback now ALSO creates a PropertyFinance
        # row for each financeless villa with a live OWNER assignment, so the
        # true gap is 1236 minus that fallback count — only derivable against
        # the live dump. `loaded_count` scopes to migrated properties so
        # rows snapshotted onto organically-created properties can't skew
        # the gap between dry-runs.
        expected_gap=1236,
        loaded_count=lambda m: m._default_manager.filter(property__legacy_id__isnull=False).count(),
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
        "SELECT COUNT(*) FROM VillaClientPrefMaster",
        GuestPreferenceType,
        "GuestPreferenceType",
    ),
    _Check(
        "SELECT COUNT(*) FROM ClientPreferenceDetails",
        GuestPreference,
        "GuestPreference",
        # Calibrated 2026-07-05: duplicate (person, preference_type,
        # quotation) triples collapse to the first occurrence (the legacy
        # table has no unique constraint), plus rows whose client resolves to
        # the no-identity sentinel path. Added when the double-run
        # convergence check caught the loader silently under-loading 16
        # quotation-linked rows (registry-order bug, since fixed — see
        # registry.py comment).
        expected_gap=93,
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
    _Check(
        # Zero-price rows are excluded (the loader skips them — the model's
        # `amount != 0` constraint forbids the write); details on deleted
        # bookings are excluded to mirror BookingLoader's DeletedAt filter.
        "SELECT COUNT(*) FROM VillaBookingDetails d"
        " JOIN VillaBooking b ON b.Id = d.BookingId AND b.DeletedAt IS NULL"
        " WHERE d.Price <> 0",
        BookingChargeItem,
        "BookingChargeItem",
        # Placeholder — recalibrate at cutover dry-run (BUG-013 precedent).
        # Error/skip rows widen this gap until fixed: no FxRate for the
        # row→booking pair, unresolvable non-zero CurrencyId, conversions
        # that quantise to zero, and details on unresolvable bookings.
        expected_gap=0,
        # Staff-created charge items (legacy_id NULL) are the live adjustment
        # mechanism and coexist with imports — count only the legacy slice,
        # or any staff write during the cutover window turns this check RED.
        loaded_count=lambda m: m._default_manager.filter(legacy_id__isnull=False).count(),
    ),
    _Check(
        # Future non-available DAYS, both sides. AvailabilityBlockLoader
        # coalesces these day rows into one BookingHold per run; the loaded
        # side re-expands each `avail-*` block back into days. The model's
        # range is half-open `[date_from, date_to)`, so a block's day count is
        # `(date_to - date_from).days` — no +1 (one grid day loads as
        # `date_to = day + 1`). Both sides move with "today": the loader
        # filters `AvailableDate >= localdate()` at LOAD time and this query
        # uses GETDATE() at RECONCILE time, so run them the same day — a day
        # crossing between the two ages rows out of the legacy side while
        # they linger in the loaded blocks (a spurious negative gap).
        "SELECT COUNT(*) FROM VillaAvailability "
        "WHERE AvailableStatus IN (30, 40, 50, 60) "
        "AND AvailableDate >= CAST(GETDATE() AS date)",
        BookingHold,
        "VillaAvailability (future days)",
        # 0 holds on the 24-Apr-2025 dump: the single future run (property
        # 133, booked 2026-07-25..2026-08-22, 29 days) sits on a property
        # that loads. Caveat: future days on UNLOADED properties, or on a
        # range an imported booking/live hold already occupies (the loader
        # skips those), would widen this gap — recalibrate at cutover.
        expected_gap=0,
        loaded_count=lambda m: sum(
            (hold.date_to - hold.date_from).days
            for hold in m._default_manager.filter(
                legacy_id__startswith=AVAILABILITY_LEGACY_PREFIX
            ).only("date_from", "date_to")
        ),
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

        Not every dump carries ZohoId on every spec table (the 24-Apr-2025
        prod dump lacks it on VillaQuotationMaster/VillaBooking): a table
        without the column gets a clearly-marked "no ZohoId column" row —
        there is nothing to backfill from, so it is informational, never a
        blocker — and the loader skipped it the same way.

        Each spec carries an `expected_gap` (default 0) mirroring the main
        table's `_Check.expected_gap`: the row only blocks when the continuity
        gap differs from the documented, accepted one (e.g. VillaMaster's
        Temenos duplicate pair — see the calibration comment on `SPECS`).
        """
        rows: list[tuple[str, int | str, int | str, int | str, int | str, int | str, str]] = []
        blockers: list[str] = []
        for spec in SyncRecordZohoLoader.SPECS:
            if not zoho_id_column_exists(cursor, spec.table):
                rows.append((f"{spec.table}.ZohoId", "-", "-", "-", "-", "-", "no ZohoId column"))
                continue
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
            ok = gap == spec.expected_gap
            if not ok:
                blockers.append(
                    f"{spec.table}.ZohoId: continuity gap {gap} != expected {spec.expected_gap} "
                    f"({loaded} loaded with a ZohoId vs {sync_records} SyncRecord(s))"
                )
            rows.append(
                (
                    f"{spec.table}.ZohoId",
                    legacy_ext,
                    loaded,
                    sync_records,
                    gap,
                    spec.expected_gap,
                    "OK" if ok else "BLOCKER",
                )
            )

        header = (
            "zoho source",
            "legacy ext id",
            "loaded",
            "sync records",
            "gap",
            "expected",
            "status",
        )
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
