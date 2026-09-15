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

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from accounts.enums import OrgType
from accounts.models import Organisation, Person, User
from accounts.models.person import PersonEmail, PersonPhone
from core.console import render_table
from data_migration.legacy_db import legacy_cursor
from data_migration.loaders._util import legacy_deleted_sql
from data_migration.loaders.availability import AVAILABILITY_LEGACY_PREFIX
from data_migration.loaders.integrations import SyncRecordZohoLoader, zoho_id_column_exists
from data_migration.loaders.people import COMPANY_PLACEHOLDERS
from data_migration.loaders.pricing import PLAN_LEGACY_PREFIX, PRICED_ROW_PREDICATE
from data_migration.loaders.sentinels import (
    CLIENT_LEGACY_PREFIX,
    SHEET_LEGACY_PREFIX,
    UNKNOWN_CLIENT_LEGACY_ID,
    UNKNOWN_LEGACY_ID,
)
from integrations.enums import SyncProvider
from integrations.models import SyncRecord
from payments.models.payment import Payment
from pricing.models.currency import Currency
from pricing.models.extra import Extra
from pricing.models.rate import RateBand, RatePeriod, RatePlan
from properties.enums import PriceBasis
from properties.models.contacts import PropertyContactAssignment
from properties.models.features import (
    Collection,
    CollectionMembership,
    Feature,
    FeatureCategory,
    PropertyFeature,
)
from properties.models.finance import PropertyFinance
from properties.models.geo import Country, NearbyPlaceType, PropertyNearbyPlace, Region
from properties.models.images import PropertyImage
from properties.models.property import Property
from properties.models.rooms import Room
from properties.models.settings import PropertySettings
from reservations.models.booking import Booking, BookingHold
from reservations.models.charge_item import BookingChargeItem
from reservations.models.enquiry import Enquiry
from reservations.models.preferences import GuestPreference, GuestPreferenceType
from reservations.models.quotation import Quotation, QuotationLine

# GAP-110 U0b night parity — per villa, the nights legacy priced (the union of
# its live, priced, non-extra rate-row spans; legacy `ToDate` is inclusive)
# must equal the nights the villa's loaded legacy periods cover. Boundary
# trims and conflict splits never change that set, so a villa with a
# mismatch lost or invented priced nights in the regroup. Same row universe
# as the loaders (`PRICED_ROW_PREDICATE`).
NIGHT_PARITY_QUERY = (
    "SELECT s.VillaId, r.FromDate, r.ToDate FROM VillaSeasonRate r "
    "JOIN VillaSeason s ON s.ID = r.SeasonId AND s.DeletedAt IS NULL "
    "JOIN VillaMaster m ON m.Id = s.VillaId AND m.DeletedAt IS NULL "
    f"WHERE {PRICED_ROW_PREDICATE}"
)

Span = tuple[date, date]


def _coalesce(spans: list[Span]) -> list[Span]:
    """Sorted, merged inclusive spans (touching or overlapping spans fuse), so
    two night sets compare as lists without materialising a `date` per night
    (an open-ended sentinel row would otherwise expand to millions)."""
    out: list[Span] = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1] + timedelta(days=1):
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def _night_count(spans: list[Span]) -> int:
    return sum((end - start).days + 1 for start, end in spans)


def _as_date(value: Any) -> date:
    return value.date() if hasattr(value, "date") else value


def night_parity_mismatches(legacy_rows: list[tuple[Any, ...]]) -> list[tuple[str, int, int]]:
    """`(villa legacy_id, legacy nights, loaded nights)` for every villa whose
    legacy priced-night set differs from its loaded legacy periods.
    `legacy_rows` are `(VillaId, FromDate, ToDate)`; UI-created periods
    (legacy_id NULL) are not part of the loaded footprint being reconciled."""
    legacy: dict[str, list[Span]] = defaultdict(list)
    for villa_id, date_from, date_to in legacy_rows:
        legacy[str(villa_id)].append((_as_date(date_from), _as_date(date_to)))
    loaded: dict[str, list[Span]] = defaultdict(list)
    periods = RatePeriod.objects.filter(legacy_id__isnull=False).values_list(
        "plan__property__legacy_id", "date_from", "date_to"
    )
    for villa_id, date_from, date_to in periods:
        loaded[str(villa_id)].append((date_from, date_to))
    mismatches: list[tuple[str, int, int]] = []
    for villa_id in sorted(legacy.keys() | loaded.keys(), key=lambda v: (len(v), v)):
        want, have = _coalesce(legacy[villa_id]), _coalesce(loaded[villa_id])
        if want != have:
            mismatches.append((villa_id, _night_count(want), _night_count(have)))
    return mismatches


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


def _eur_legacy_id(model: type[Any]) -> int:
    """The legacy id stamped on EUR, or 0 when absent/unstamped/non-numeric."""
    legacy_id = (
        model._default_manager.filter(code="EUR").values_list("legacy_id", flat=True).first()
    )
    return int(legacy_id) if legacy_id and legacy_id.isdigit() else 0


_COMPANY_PLACEHOLDERS_SQL = ", ".join(f"'{p}'" for p in sorted(COMPANY_PLACEHOLDERS))


_CHECKS: list[_Check] = [
    _Check(
        "SELECT COUNT(*) FROM VillaCountry",
        Country,
        "Country (legacy)",
        # Negative gap: loaded > legacy. Migration properties.0002 pre-seeds
        # 249 canonical ISO-3166 countries (legacy_id NULL); the 23 legacy
        # VillaCountry rows are matched onto that seed by iso2 rather than
        # adding to it. Plus the unknown_country `XX` sentinel, created
        # lazily by the first fallback (the dump's iso-less junk rows always
        # trigger it). The seeded table dwarfs the 23 legacy rows, so the gap
        # is structurally negative. BUG-030 §6: 23 - (249 + 1) = -227.
        # Before, legacy 24 ("England", iso2 `UK`) minted a 250th row
        # (-228); `_resolve_iso2` now maps `UK` → GB and rejects any non-ISO
        # code, so no extra Country row is ever created. The dev dump's
        # "Dev Country" 25 (`DC`, live) is skipped the same way; it is not in
        # the 23-row prod dump (DRYRUN_LOG) — GAP-108 confirms on the live
        # dump before pinning for good.
        expected_gap=-227,
    ),
    _Check(
        # GAP-107: legacy `IsActive = 1` countries that are not soft-deleted
        # vs migrated countries loaded active. Parity, not a strict
        # invariant: a live legacy row CountryLoader cannot seed-match (an
        # iso-less row absorbed by the `XX` sentinel, or a second live row on
        # an already-claimed iso2, which is skipped) counts here but loads
        # nowhere / inactive. Calibrated 2026-09-10 (24-Apr-2025 dump): 6/6,
        # gap 0 — all six live rows (GR, IT, FR, MA, ES, KE) seed-match; the
        # only iso2 duplicates (France 3/13, India 11/20) involve deleted
        # rows. BUG-030 §6: England (24, `UK`) resolves to GB and is skipped
        # (6 holds the seed); `country_for_legacy_id` aliases its FKs, so
        # there is no post-load merge step any more.
        f"SELECT COUNT(*) FROM VillaCountry WHERE IsActive = 1 AND NOT {legacy_deleted_sql()}",
        Country,
        "Country (active)",
        loaded_count=lambda m: (
            m._default_manager.filter(legacy_id__isnull=False, is_active=True)
            .exclude(iso2="XX")
            .count()
        ),
    ),
    # GAP-107 adds no shift to the bare total: deleted regions still load
    # (retired in place, never skipped). Its pre-existing shifters remain —
    # blank-name rows are skipped by the loader, and the loaded side counts
    # the `unknown-xx` sentinel and staff-created rows.
    _Check("SELECT COUNT(*) FROM VillaRegion", Region, "Region"),
    # The two slices below say WHICH imported rows came in active. Together
    # they pin the retired count too (retired = imported - active on both
    # sides), so a single misclassification cannot hide inside the total;
    # an equal-and-opposite swap still can — these are counts, not row
    # diffs. A region is live iff its own row is not deleted AND it sits
    # under a live, `IsActive = 1` country (RegionLoader derives `is_active`
    # from the loaded Country row). Same seed-match caveat as
    # `Country (active)` above. Calibrated 2026-09-10 (24-Apr-2025 dump):
    # imported 64/64, active 42/42 (22 retired: 9 own-deleted under live
    # countries + 13 under deleted countries), both gap 0.
    _Check(
        "SELECT COUNT(*) FROM VillaRegion r WHERE LTRIM(RTRIM(ISNULL(r.Name, ''))) <> ''",
        Region,
        "Region (imported)",
        loaded_count=lambda m: (
            m._default_manager.filter(legacy_id__isnull=False)
            .exclude(legacy_id=UNKNOWN_LEGACY_ID)
            .count()
        ),
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaRegion r JOIN VillaCountry c ON c.Id = r.CountryId "
        f"WHERE LTRIM(RTRIM(ISNULL(r.Name, ''))) <> '' AND NOT {legacy_deleted_sql('r.')} "
        f"AND NOT {legacy_deleted_sql('c.')} AND c.IsActive = 1",
        Region,
        "Region (active)",
        loaded_count=lambda m: (
            m._default_manager.filter(legacy_id__isnull=False, is_active=True)
            .exclude(legacy_id=UNKNOWN_LEGACY_ID)
            .count()
        ),
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaCurrency",
        Currency,
        "Currency",
        expected_gap=4,  # junk rows (HTFG/RUPEE/RS) with zero FK references.
    ),
    _Check(
        # BUG-028: deleted VillaCurrency rows load retired, not skipped, so
        # the bare total above cannot tell whether the live rows came in
        # active. Dump (24-Apr-2025): 3 live (GBP 1, EUR 3, USD 6).
        f"SELECT COUNT(*) FROM VillaCurrency WHERE NOT {legacy_deleted_sql()}",
        Currency,
        "Currency (active)",
        loaded_count=lambda m: m._default_manager.filter(
            legacy_id__isnull=False, is_active=True
        ).count(),
    ),
    _Check(
        # BUG-028 value invariant: EUR must carry the LIVE legacy row's id
        # (Id 3 on the dump — every settings/rate/booking row points there),
        # not the soft-deleted Id 2 twin. A gap names the wrong claimant.
        f"SELECT ISNULL(MIN(Id), 0) FROM VillaCurrency WHERE Code = 'EUR' "
        f"AND NOT {legacy_deleted_sql()}",
        Currency,
        "Currency EUR legacy_id (live row)",
        loaded_count=lambda m: _eur_legacy_id(m),
    ),
    _Check("SELECT COUNT(*) FROM VillaNearByLocationType", NearbyPlaceType, "NearbyPlaceType"),
    _Check("SELECT COUNT(*) FROM VillaFeaturesCategory", FeatureCategory, "FeatureCategory"),
    _Check(
        "SELECT COUNT(*) FROM VillaFeatures WHERE DeletedAt IS NULL",
        Feature,
        "Feature",
    ),
    _Check(
        # BUG-030 §11: the through table (the largest loaded table after
        # images) gets its own check. Legacy side = distinct (villa, feature)
        # pairs after the loader's remap: a deleted feature resolves to the
        # lowest-Id live, named, categorised namesake (the T-SQL twin of
        # `_feature_twins_by_name`), an unmatched one drops out; villas
        # mirror PropertyLoader's filter (live, named). Loaded side = manual
        # links whose property AND feature are legacy rows — GAP-067
        # `recompute_derived_features` (`is_derived=True`) and staff links on
        # organic rows never count (a staff link between two legacy rows
        # would). Structural gap 0; known shifters, all itemised by GAP-108
        # on the live dump: a live feature FeatureLoader skips (blank name,
        # or its FIRST category mapping unloaded — the T-SQL twin rule only
        # needs a named category on ANY mapping), a slug collision between
        # live namesakes (the loader keeps the lowest Id, same as MIN here),
        # and whitespace/collation differences between Python `.strip()
        # .lower()` and `LOWER(LTRIM(RTRIM()))`. Pinned 0 pending that dry
        # run, which is the first execution of this SQL (the reference dump:
        # 10 031 live pairs + the remapped ones).
        "SELECT COUNT(DISTINCT CONCAT(x.VillaId, '-', x.ResolvedId)) FROM ("
        "SELECT m.VillaId, CASE WHEN f.DeletedAt IS NULL THEN f.Id ELSE ("
        "SELECT MIN(t.Id) FROM VillaFeatures t "
        "WHERE t.DeletedAt IS NULL AND LTRIM(RTRIM(t.Name)) <> '' "
        "AND LOWER(LTRIM(RTRIM(t.Name))) = LOWER(LTRIM(RTRIM(f.Name))) "
        "AND EXISTS (SELECT 1 FROM VillaFeaturesCategoryMappings cm "
        "JOIN VillaFeaturesCategory c ON c.Code = cm.CategoryId "
        "WHERE cm.FeatureId = t.Id AND LTRIM(RTRIM(ISNULL(c.Name, ''))) <> '')"
        ") END AS ResolvedId "
        "FROM VillaFeaturesMappings m "
        "JOIN VillaFeatures f ON f.Id = m.FeatureId "
        "JOIN VillaMaster v ON v.Id = m.VillaId "
        "WHERE v.DeletedAt IS NULL AND LTRIM(RTRIM(ISNULL(v.Name, ''))) <> ''"
        ") x WHERE x.ResolvedId IS NOT NULL",
        PropertyFeature,
        "PropertyFeature",
        loaded_count=lambda m: m._default_manager.filter(
            is_derived=False,
            property__legacy_id__isnull=False,
            feature__legacy_id__isnull=False,
        ).count(),
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
        # GAP-089: the spreadsheet importers' `sheet-` persons have no legacy
        # twin either.
        loaded_count=lambda m: (
            m._default_manager.exclude(legacy_id__startswith=CLIENT_LEGACY_PREFIX)
            .exclude(legacy_id__startswith=SHEET_LEGACY_PREFIX)
            .count()
        ),
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaContactEmail",
        PersonEmail,
        "PersonEmail",
        # GAP-045: ClientLoader also reconciles VillaClientDetails email
        # columns onto the `client-` Person slice, but the legacy side here
        # counts only VillaContactEmail — exclude client-owned channels
        # (mirrors the "Person (owner/agent)" slice split above) or every
        # client email shows as a negative gap (dry-run 1: 30 of them). The
        # GAP-089 `sheet-` persons' channels are excluded for the same reason.
        loaded_count=lambda m: (
            m._default_manager.exclude(contact__legacy_id__startswith=CLIENT_LEGACY_PREFIX)
            .exclude(contact__legacy_id__startswith=SHEET_LEGACY_PREFIX)
            .count()
        ),
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaContactTele",
        PersonPhone,
        "PersonPhone",
        # Same client- and sheet-slice exclusions as PersonEmail above.
        loaded_count=lambda m: (
            m._default_manager.exclude(contact__legacy_id__startswith=CLIENT_LEGACY_PREFIX)
            .exclude(contact__legacy_id__startswith=SHEET_LEGACY_PREFIX)
            .count()
        ),
    ),
    _Check(
        # GAP-046: every distinct (case/space-normalised) VillaContact.Company
        # becomes one Organisation(agency) via organisation_for_company_name, so
        # the loader actually created the orgs (catches a silent "zero orgs"
        # regression). SQL Server's default collation folds case + trailing
        # space but NOT internal whitespace, so the rare "Dune  Travel" vs
        # "Dune Travel" pair the helper merges shows as a small positive gap —
        # bump expected_gap at the first dry-run if so. Blank companies are
        # excluded both sides (helper returns None → no org), and so are the
        # BUG-030 §15 placeholders (`COMPANY_PLACEHOLDERS`: 226/233 are "NA").
        "SELECT COUNT(DISTINCT LTRIM(RTRIM(Company))) FROM VillaContact "
        "WHERE LTRIM(RTRIM(ISNULL(Company, ''))) <> '' "
        f"AND UPPER(LTRIM(RTRIM(Company))) NOT IN ({_COMPANY_PLACEHOLDERS_SQL})",
        Organisation,
        "Organisation (agency)",
        # GAP-089: `import_enquiry_sheet` mints agencies from the sheet's
        # `Trade` column, stamped `sheet-org-…` — no VillaContact twin.
        loaded_count=lambda m: (
            m._default_manager.filter(org_type=OrgType.AGENCY)
            .exclude(legacy_id__startswith=SHEET_LEGACY_PREFIX)
            .count()
        ),
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
        # BUG-030 §13 (24-Apr-2025 dump): 308 = 3 duplicate (collection,
        # villa) pairs + 22 memberships on deleted villas + 283 live
        # memberships of the five collections deleted together on
        # 2024-05-28 ("Chef Included" 66, "Exceptional Design" 55, "Walk to
        # restaurants" 34, "Water Front" 59, "WALK TO THE BEACH" 67), which
        # CollectionLoader drops (decision 2026-09-11: drop, record here).
        expected_gap=308,
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
        # gap.
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
        # GAP-110: a RatePlan is one (villa, currency) regime, not a season,
        # so both sides count VILLAS. Legacy = live villas with ≥1 live priced
        # rate row (the loaders' shared predicate, so rate-less seasons drop
        # out of both sides). Loaded = distinct villas owning a `villa:`-keyed
        # regime plan that actually carries ≥1 legacy period (a plan the band
        # loader couldn't populate is not a loaded villa; staff-created plans
        # never count). Gap = villas the loader couldn't resolve (no Property,
        # no currency) — structurally ≥ 0. PLACEHOLDER 0: recalibrate at the
        # first post-GAP-110 dry-run (see CUTOVER.md); the pre-regroup numbers
        # (710 seasons → 521 plans, gap 67) no longer apply.
        "SELECT COUNT(DISTINCT s.VillaId) FROM VillaSeason s "
        "JOIN VillaMaster m ON m.Id = s.VillaId AND m.DeletedAt IS NULL "
        "WHERE s.DeletedAt IS NULL AND EXISTS ("
        f" SELECT 1 FROM VillaSeasonRate r WHERE r.SeasonId = s.ID AND {PRICED_ROW_PREDICATE})",
        RatePlan,
        "RatePlan (villas with a loaded regime)",
        expected_gap=0,
        loaded_count=lambda m: (
            m._default_manager.filter(
                legacy_id__startswith=PLAN_LEGACY_PREFIX, periods__legacy_id__isnull=False
            )
            .values("property_id")
            .distinct()
            .count()
        ),
    ),
    _Check(
        # SMELL-021: legacy cannot express a NET basis (no such column;
        # `RatesModel.Calculate()` treats every entered rate as gross), so the
        # loader stamps GROSS on every imported plan. Legacy side is a constant
        # 0; any imported plan carrying NET means the stamp regressed to the
        # model default (or was hand-edited under a legacy_id) — a BLOCKER.
        "SELECT 0",
        RatePlan,
        "RatePlan non-GROSS basis (must be 0)",
        loaded_count=lambda m: (
            m._default_manager.filter(legacy_id__isnull=False)
            .exclude(price_basis=PriceBasis.GROSS)
            .count()
        ),
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
        # Recalibrated 2026-09-14 (BUG-028, post-GAP-110) against the
        # 24-Apr-2025 prod dump (DRYRUN_LOG run 4; replayed through the
        # loader's own pipeline, zero residual). Legacy 7333 = 7082
        # VillaSeasonRate parents + 251 occupancy children; loaded 2841 =
        # 2593 simple + 12 #seg fragments + 235 occ-* bands + 1 occ-fb-* gap
        # fallback. Itemised:
        #   + 1154  rows outside the loader's source query (deleted/dangling
        #           season or deleted villa — GAP-110 moved that filter into
        #           SQL; run 1 counted them among "no RatePlan")
        #   +  108  occupancy-banded parents replaced by their band expansion
        #   + 3099  priceless non-POA rows (BUG-028: only NightlyPrice /
        #           WeeklyPrice > 0 or IsPOA count — 792 of these are
        #           Price-only or 0.00 rows that used to load)
        #   +    9  rows on live seasons with no regime plan
        #   +  106  synthetic gap fallbacks emptied by capacity (bands
        #           already cover 1..cap)
        #   +  136  flattener-shadowed sources (cross-season within a regime
        #           since GAP-110)
        #   -  108  synthetic occ-fb-* fallback rows added by expansion
        #   -   12  #seg fragments added by the flattener
        # Junk dates / invalid occ children / resolver drops: all 0 on this
        # dump. Recalibrate on a newer dump — the mix (especially priceless
        # rows and unloaded seasons) moves with the data, not the code.
        expected_gap=4492,
    ),
    _Check(
        # BUG-028: legacy quotes treat a 0.00 (or negative) price as absent, so
        # an imported non-POA band carrying one would quote a free stay. The
        # `rateband_has_price_or_poa` constraint already rules out both-NULL;
        # staff-created bands (no legacy_id) are out of scope.
        "SELECT 0",
        RateBand,
        "RateBand non-POA priced <= 0 (must be 0)",
        loaded_count=lambda m: (
            m._default_manager.filter(legacy_id__isnull=False, is_poa=False)
            .filter(Q(nightly__lte=0) | Q(weekly__lte=0))
            .count()
        ),
    ),
    _Check(
        # BUG-028 §5 decision: legacy quotes ignore `IsApprove`, so every
        # imported band loads approved (the legacy flag survives in notes and
        # in overlap precedence). The engine prices only approved bands.
        "SELECT 0",
        RateBand,
        "RateBand unapproved imported (must be 0)",
        loaded_count=lambda m: m._default_manager.filter(
            legacy_id__isnull=False, is_approved=False
        ).count(),
    ),
    _Check(
        # GAP-107: the extras catalogue — the `IsExTra = 1` rows the RateBand
        # check above excludes, ported by ExtraLoader (CUTOVER.md §4i). The
        # legacy side mirrors the loader's `DeletedAt IS NULL` AND
        # PropertyLoader's villa filter (`m.DeletedAt IS NULL` + non-blank
        # name), so extras on villas that never load do not count: on the
        # 24-Apr-2025 dump that is 12 of 96 (11 on soft-deleted villas + 1 on
        # villa 249, the blank-name row) -> 84/84, gap 0, data-independent.
        # Loaded side counts ported rows still active — a full run retires
        # (keeps `legacy_id`, flips `is_active`) exactly the rows the legacy
        # filter drops. Shifters: a no-currency skip, or staff deactivating a
        # ported extra in the SPA (widens the gap by one each).
        "SELECT COUNT(*) FROM VillaSeasonRate r "
        "JOIN VillaMaster m ON m.Id = r.VillaId "
        "WHERE r.DeletedAt IS NULL AND r.IsExTra = 1 "
        "AND m.DeletedAt IS NULL AND LTRIM(RTRIM(ISNULL(m.Name, ''))) <> ''",
        Extra,
        "Extra",
        expected_gap=0,
        loaded_count=lambda m: m._default_manager.filter(
            legacy_id__isnull=False, is_active=True
        ).count(),
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
        # satisfy the now-mandatory Quotation.enquiry FK for legacy quotations
        # that carried no enquiry of their own (no booking-synth quotations
        # since GAP-108 unregistered the booking loaders). -8 on the 24-Apr dump
        # included 3 BookingLoader.ensure_enquiry rows, hence -5.
        expected_gap=-5,  # provisional — pinned in GAP-108 dry run
        # GAP-089: `import_enquiry_sheet` adds ~2.4k historic `sheet-enquiry-`
        # rows with no VillaEnquire twin — leave them out of the comparison.
        loaded_count=lambda m: m._default_manager.exclude(
            legacy_id__startswith=SHEET_LEGACY_PREFIX
        ).count(),
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaFinance WHERE VillaId IS NOT NULL",
        PropertyFinance,
        "PropertyFinance",
        # 1236 = legacy rows the per-villa pass does not port, itemised at
        # the GAP-107 dry-run (2026-09-10, 24-Apr-2025 dump; DRYRUN_LOG.md):
        #   1526  `VillaId IS NOT NULL` (= every row; the column is NOT NULL)
        #  -1089  `VillaId = 0`: 413 contact-default templates (`ParentId`
        #         NULL) + 676 parent-child overrides with no villa
        #  - 146  `VillaId > 0` on soft-deleted villas
        #  -   1  `VillaId > 0` on villa 249, the blank-name row the
        #         property loader skips (the `Property` gap of 1)
        #  = 290  stamped per-villa rows (311 override rows with `VillaId > 0`
        #         ARE ported as the villa's own row — do not exclude ParentId)
        # Loaded side (GAP-107): only rows the per-villa pass stamped with
        # `legacy_id` = `VillaFinance.Id`. The GAP-070 owner-contact fallback
        # rows and `snapshot_defaults` rows carry NULL, so neither moves the
        # gap between dry-runs (GAP-073 measured 1235 while fallback rows
        # were counted). `loaded = 0` means a DB loaded before migration
        # properties.0008 — re-run `loadlegacy property_finance` (CUTOVER.md
        # §6f). Stale caveat: a stamped row whose legacy twin was later
        # hard-deleted keeps its legacy_id (no sweep, `VillaFinance` has no
        # `DeletedAt`) — recalibrate on a fresh load of a newer dump.
        expected_gap=1236,
        loaded_count=lambda m: m._default_manager.filter(legacy_id__isnull=False).count(),
    ),
    _Check(
        # BUG-028: the type-code maps once keyed 1/2 while legacy stores 10/20,
        # so every calculation type loaded NULL — and NULL silently falls
        # through to `_POLICY_FALLBACKS` (sec-dep FIXED), turning "10 %" into
        # EUR 10. Every legacy block resolves a type (own, or the CPD
        # substitution), so a stamped row with any NULL type is a regression.
        "SELECT 0",
        PropertyFinance,
        "PropertyFinance NULL calculation type (must be 0)",
        loaded_count=lambda m: (
            m._default_manager.filter(legacy_id__isnull=False)
            .filter(
                Q(commission_calculation_type__isnull=True)
                | Q(deposit_calculation_type__isnull=True)
                | Q(interim_calculation_type__isnull=True)
                | Q(security_deposit_calculation_type__isnull=True)
            )
            .count()
        ),
    ),
    _Check(
        # BUG-028: a flagged `IsDefaultSettingCurrencyId` stores 0 (or the
        # deleted EUR twin, Id 2) and must take the CPD currency; with the live
        # EUR claimed by `CurrencyLoader` every imported villa resolves one.
        # Organic properties (no legacy_id) may legitimately be unset.
        "SELECT 0",
        PropertySettings,
        "PropertySettings without currency (must be 0)",
        loaded_count=lambda m: m._default_manager.filter(
            property__legacy_id__isnull=False, currency__isnull=True
        ).count(),
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaQuotationMaster WHERE DeletedAt IS NULL",
        Quotation,
        "Quotation",
        # Was -3 while BookingLoader synthesised a hidden ACCEPTED quotation per
        # legacy booking; with the booking loaders unregistered (GAP-108) every
        # loaded quotation has a live legacy twin.
        expected_gap=0,  # provisional — pinned in GAP-108 dry run
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaQuotationDetails",
        QuotationLine,
        "QuotationLine",
        # Was -2 (lines on the booking-synth quotations, gone since GAP-108).
        expected_gap=0,  # provisional — pinned in GAP-108 dry run
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
        # Calibrated 2026-07-05 (167 legacy rows load as 74). BUG-030 §30:
        # the gap is quotation-context loss, not bad data — 126 rows carry a
        # QuotationMasterId with no VillaQuotationMaster row (ids up to 541;
        # the table's max Id is 20, some are VillaEnquire ids), load with
        # quotation=None, and then collapse on the (person, preference_type,
        # NULL) unique triple with each other; the remainder are genuine
        # duplicate triples (the legacy table has no unique constraint). The
        # loader logs the unresolved count
        # (`data_migration.preference_quotation_unresolved`).
        expected_gap=93,
    ),
    # Booking / Payment / BookingChargeItem: the loaders are UNREGISTERED
    # (GAP-089, GAP-108) — bookings come from the Past Bookers sheet, whose
    # rows carry no legacy_id. Any row stamped with a legacy_id means a
    # booking loader ran against the legacy DB, which is a blocker. Organic
    # rows (sheet imports, staff bookings/charge lines/payments) never count.
    _Check(
        "SELECT 0",
        Booking,
        "Booking with legacy_id (must be 0)",
        loaded_count=lambda m: m._default_manager.filter(legacy_id__isnull=False).count(),
    ),
    _Check(
        "SELECT 0",
        Payment,
        "Payment with legacy_id (must be 0)",
        loaded_count=lambda m: m._default_manager.filter(legacy_id__isnull=False).count(),
    ),
    _Check(
        "SELECT 0",
        BookingChargeItem,
        "BookingChargeItem with legacy_id (must be 0)",
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
        # Duplicate day rows count once, as their latest edit — the same
        # dedupe-then-filter as `coalesce_runs` (BUG-029). Blocking statuses
        # mirror `BLOCKING_STATUSES` (BUG-030 §31: 0/NULL Unknown and
        # 6 BookedExt block too).
        "SELECT COUNT(*) FROM ("
        "SELECT AvailableStatus, ROW_NUMBER() OVER (PARTITION BY PropertyId, "
        "CAST(AvailableDate AS date) ORDER BY COALESCE(UpdatedAt, CreatedAt) DESC, Id DESC) AS rn "
        "FROM VillaAvailability WHERE AvailableDate >= CAST(GETDATE() AS date)"
        ") latest WHERE rn = 1 AND ISNULL(AvailableStatus, 0) IN (0, 6, 30, 40, 50, 60)",
        BookingHold,
        "VillaAvailability (future days)",
        # expected_gap = legacy blocking days - loader-written hold days
        #              = days trimmed under imported bookings / live staff
        #                holds (the loader logs `trimmed_days`)
        #              + days on unloaded properties (logged as skips)
        #              + days of runs that errored (`report.errors`).
        # 0 on the reference dump: its single future run (property 133,
        # 2026-07-25..2026-08-22, 29 days) has no imported booking under it.
        # GAP-108 recalibrates on the live dump, where the status-0
        # whole-calendar blocks (BUG-030 §31) will carry bookings.
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
            blockers += self._night_parity_section(cursor)
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

    def _night_parity_section(self, cursor: Any) -> list[str]:
        """GAP-110 U0b: per-villa priced-night parity between legacy rate rows
        and loaded legacy periods. Lists every mismatched villa (so a residue
        can be itemised on the dump, never waved through as a number) and
        returns one blocker per villa; expected residue is zero."""
        cursor.execute(NIGHT_PARITY_QUERY)
        mismatches = night_parity_mismatches(cursor.fetchall())
        self.stdout.write("\nRatePeriod night parity (villas whose priced nights differ):")
        if not mismatches:
            self.stdout.write("  OK — every villa's loaded periods cover exactly its legacy nights")
            return []
        header = ("villa legacy_id", "legacy nights", "loaded nights", "status")
        self.stdout.write(
            render_table(header, [(v, want, have, "BLOCKER") for v, want, have in mismatches])
        )
        return [
            f"RatePeriod night parity: villa {v} legacy {want} nights, loaded {have}"
            for v, want, have in mismatches
        ]

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

        Limitation: this compares counts, not values.

        Not every dump carries ZohoId on every spec table (the 24-Apr-2025
        prod dump lacks it on VillaQuotationMaster): a table
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
