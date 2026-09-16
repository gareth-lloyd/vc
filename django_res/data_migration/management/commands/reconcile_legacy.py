"""Compare legacy row counts against loaded Django row counts.

Prints a table and exits non-zero if any row's gap doesn't match its
documented expectation:

    table                  legacy   loaded   gap    expected   status
    VillaMaster            441      440      1      1          OK
    VillaPropertyImages    13089    13089    0      0          OK
    CollectionMembership   1234     926      308    308        OK
    ...

The list of (legacy_table_or_query, django_model) pairs is explicit so
gaps mirror loader scope (e.g. VillaMaster's `live_villa_sql` filter is
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
from django.db.models import Count, Q
from django.db.models.functions import Trim, Upper

from accounts.enums import OrgType
from accounts.models import Organisation, Person, User
from accounts.models.person import PersonEmail, PersonPhone
from core.console import render_table
from data_migration.archive_stays import ARCHIVE_ROWS_SQL, classify, group_rows
from data_migration.legacy_db import legacy_cursor, rows_as_dicts
from data_migration.loaders._util import legacy_active_sql, legacy_deleted_sql, live_villa_sql
from data_migration.loaders.availability import AVAILABILITY_LEGACY_PREFIX
from data_migration.loaders.integrations import SyncRecordZohoLoader, zoho_id_column_exists
from data_migration.loaders.people import COMPANY_PLACEHOLDERS
from data_migration.loaders.pricing import (
    PLAN_LEGACY_PREFIX,
    PRICED_ROW_PREDICATE,
    VALID_OCCUPANCY_BAND_PREDICATE,
)
from data_migration.loaders.sentinels import (
    CLIENT_LEGACY_PREFIX,
    SHEET_LEGACY_PREFIX,
    UNKNOWN_CLIENT_LEGACY_ID,
    UNKNOWN_LEGACY_ID,
)
from data_migration.relink import classify_enquiry, unlinked_legacy_enquiries
from integrations.enums import SyncProvider
from integrations.models import SyncRecord
from payments.models.payment import Payment
from pricing.models.currency import Currency
from pricing.models.extra import Extra
from pricing.models.rate import RateBand, RatePeriod, RatePlan
from properties.enums import PriceBasis
from properties.models.capacity import PropertyCapacity
from properties.models.contacts import PropertyContactAssignment
from properties.models.defaults import PropertyDefaults
from properties.models.descriptions import PropertyDescription
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
from properties.models.location import PropertyLocation
from properties.models.property import Property
from properties.models.rooms import Room, RoomBeds
from properties.models.services import PropertyService
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
    f"JOIN VillaMaster m ON m.Id = s.VillaId AND {live_villa_sql('m.')} "
    f"WHERE {PRICED_ROW_PREDICATE}"
)

# GAP-108 — the RateBand check's legacy universe. Same row set the loaders
# see: priced, non-extra, live rate rows on a live season of a loaded villa
# (`_RB_SRC` + `PRICED_ROW_PREDICATE`), with every occupancy-flagged parent
# replaced by its VALID VillaOccupencyPrice children. The validity rule is
# imported (`VALID_OCCUPANCY_BAND_PREDICATE`), not restated, so it cannot drift
# from the Python guard in `_prepare_occupancy_rows` that defines it.
# A parent whose children are ALL junk keeps counting as itself here, which
# matches the loader passing it through as a plain base-weekly row — but only
# when the parent has a price of its own. A priceless `IsOccupationPrice` parent
# admitted by `PRICED_ROW_PREDICATE` solely because some child has a positive
# price, whose every child is out of range, is counted here and then dropped by
# `_row_to_band` for want of a price: it is neither loaded nor shadowed, so it
# would break the itemisation identity below by one. Zero such rows on ResProd
# (it is the `_row_to_band` rejection term); look here first if a recalibration
# on a newer dump comes up one short.
_RB_SRC = (
    "FROM VillaSeasonRate r "
    "JOIN VillaSeason s ON s.ID = r.SeasonId AND s.DeletedAt IS NULL "
    f"JOIN VillaMaster m ON m.Id = s.VillaId AND {live_villa_sql('m.')} "
)


def _rate_band_source_sql(extra_predicate: str = "") -> str:
    """COUNT of the RateBand loader's source universe (see the RateBand check):
    non-occupancy priced parents + valid occupancy children. `extra_predicate`
    narrows BOTH halves to a slice of that same universe (GAP-114: the carried
    seasons), so a slice check can never drift from the whole."""
    narrow = f" AND {extra_predicate}" if extra_predicate else ""
    return (
        f"SELECT (SELECT COUNT(*) {_RB_SRC}"
        f" WHERE {PRICED_ROW_PREDICATE}{narrow}"
        " AND NOT (ISNULL(r.IsOccupationPrice, 0) = 1 AND EXISTS"
        f"  (SELECT 1 FROM VillaOccupencyPrice o"
        f"   WHERE o.VillaSeasonRateId = r.ID AND {VALID_OCCUPANCY_BAND_PREDICATE})))"
        f" + (SELECT COUNT(*) {_RB_SRC}"
        f"   JOIN VillaOccupencyPrice o ON o.VillaSeasonRateId = r.ID"
        f"   WHERE {PRICED_ROW_PREDICATE}{narrow} AND ISNULL(r.IsOccupationPrice, 0) = 1"
        f"   AND {VALID_OCCUPANCY_BAND_PREDICATE})"
    )


# GAP-114: `VillaSeason.CarriedRates` is a nullable ResProd-only bit; the
# loader reads NULL as "not carried".
CARRIED_RATES_PREDICATE = "ISNULL(s.CarriedRates, 0) = 1"

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
    # Optional override for the loaded-row count. Defaults to the rows the
    # loader stamped (`legacy_id IS NOT NULL`, GAP-108): organic rows (staff
    # writes, `createsuperuser`) must never move a gap between dry runs.
    # Supply a callable when the model is partitioned by a `legacy_id` prefix
    # (GAP-045 D5-3: VillaContact and VillaClientDetails both land in
    # `accounts.Person`, so each check counts only its own slice), has no
    # `legacy_id`, or legitimately counts unstamped rows. The callable takes
    # the model and returns the count.
    loaded_count: Callable[[type[Any]], int] | None = None

    def count_loaded(self) -> int:
        if self.loaded_count is not None:
            return self.loaded_count(self.model)
        return int(self.model._default_manager.filter(legacy_id__isnull=False).count())


def _relinkable_sentinel_quotations(model: type[Any]) -> int:
    """GAP-112: loaded quotations on the unknown-client sentinel that
    `relink_enquiry_customers` would move — their enquiry already has a person,
    or is one the pass would link now. Independent of the sheet contents: it
    reads 0 once the relink has run (the sheet imports raise it, and so can
    `QuotationLoader`'s back-fill of an enquiry from a later quotation)."""
    stranded = model._default_manager.filter(
        person__legacy_id=UNKNOWN_CLIENT_LEGACY_ID, legacy_id__isnull=False
    )
    relinkable = [
        enquiry.pk
        for enquiry in unlinked_legacy_enquiries().filter(pk__in=stranded.values("enquiry"))
        if classify_enquiry(enquiry)[0] == "relinked"
    ]
    return int(
        stranded.filter(enquiry__person__isnull=False)
        .exclude(enquiry__person__legacy_id=UNKNOWN_CLIENT_LEGACY_ID)
        .count()
        + stranded.filter(enquiry__in=relinkable).count()
    )


def _numeric_legacy_id(legacy_id: str | None) -> int:
    return int(legacy_id) if legacy_id and legacy_id.isdigit() else 0


def _eur_legacy_id(model: type[Any]) -> int:
    """The legacy id stamped on EUR, or 0 when absent/unstamped/non-numeric."""
    return _numeric_legacy_id(
        model._default_manager.filter(code="EUR").values_list("legacy_id", flat=True).first()
    )


def _defaults_currency_legacy_id(model: type[Any]) -> int:
    """The legacy id of the PropertyDefaults singleton's currency, or 0 when
    the singleton / its currency / the stamp is absent. Never `get_solo()`:
    reconcile must not write."""
    return _numeric_legacy_id(
        model._default_manager.filter(pk=1).values_list("currency__legacy_id", flat=True).first()
    )


def _one_per_loaded_property(model: type[Any]) -> int:
    return int(model._default_manager.filter(property__legacy_id__isnull=False).count())


# PropertyLoader writes one location, capacity and settings row per property
# it loads, so those satellites share the Property check's legacy side.
_LIVE_VILLAS_QUERY = f"SELECT COUNT(*) FROM VillaMaster WHERE {live_villa_sql()}"


def _non_blank_sql(column: str) -> str:
    # T-SQL LTRIM/RTRIM strip only spaces while the loader's Python `.strip()`
    # also strips tabs/newlines, so a whitespace-only (non-space) value counts
    # here but loads nothing — a positive gap. 0 such values on ResProd
    # (2026-09-15: the T-SQL sum and a Python replay both give 1 049).
    return f"LEN(LTRIM(RTRIM(ISNULL({column}, '')))) > 0"


def _section_case_sql(*columns: str) -> str:
    """1 when any of `columns` is non-blank (a section the loader writes)."""
    condition = " OR ".join(_non_blank_sql(c) for c in columns)
    return f"CASE WHEN {condition} THEN 1 ELSE 0 END"


# PropertyLoader `_write_descriptions`: one row per non-blank section — five
# VillaMaster columns, plus WEB_DESCRIPTION (WebDesc1/2) and LOCATION
# (Location1/2) from the villa's MAX(Id) VillaPropertyImagesDescription row,
# over the same villas the loader reads (`live_villa_sql`).
_DESCRIPTION_SECTIONS = (
    ("m.OverView",),
    ("m.HouseRules",),
    ("m.FeatureDescription",),
    ("m.RoomDescription",),
    ("m.Notes",),
    ("d.WebDesc1", "d.WebDesc2"),
    ("d.Location1", "d.Location2"),
)
_DESCRIPTION_QUERY = (
    "SELECT ISNULL(SUM("
    + " + ".join(_section_case_sql(*cols) for cols in _DESCRIPTION_SECTIONS)
    + "), 0) FROM VillaMaster m "
    "LEFT JOIN VillaPropertyImagesDescription d ON d.Id = ("
    "SELECT MAX(d2.Id) FROM VillaPropertyImagesDescription d2 WHERE d2.VillaId = m.Id) "
    f"WHERE {live_villa_sql('m.')}"
)


_COMPANY_PLACEHOLDERS_SQL = ", ".join(f"'{p}'" for p in sorted(COMPANY_PLACEHOLDERS))


_CHECKS: list[_Check] = [
    _Check(
        "SELECT COUNT(*) FROM VillaCountry",
        Country,
        "Country (legacy)",
        # Negative gap: loaded > legacy. Migration properties.0002 pre-seeds
        # 249 canonical ISO-3166 countries (legacy_id NULL); the legacy
        # VillaCountry rows are matched onto that seed by iso2 rather than
        # adding to it. The seeded table dwarfs them, so the gap is
        # structurally negative.
        # GAP-108 U8c: the `unknown_country` XX sentinel is EXCLUDED, as it is
        # on `Country (active)` below and on the Region checks. It is minted
        # lazily by the first unresolvable-country fallback, so baking it into
        # the constant would turn this check RED on a dump whose every
        # VillaCountry row resolves to an ISO code. Excluded by `iso2`, not
        # `legacy_id`: CountryLoader re-points the sentinel's legacy_id onto a
        # real legacy row.
        # Before, legacy 24 ("England", iso2 `UK`) minted a 250th row
        # (-228); `_resolve_iso2` now maps `UK` → GB and rejects any non-ISO
        # code, so no extra Country row is ever created.
        # GAP-108 pinned on ResProd (13-Aug-2026): 24 legacy rows — the 23 of
        # the old dump plus Id 25 `Sync_Country`, a soft-deleted sync artefact
        # created and deleted on 26-Apr-2025 (just after that dump) whose name
        # resolves to no ISO code, so `_resolve_iso2` rejects it like England
        # — against the 249 seeded rows ⇒ 24 - 249 = -225. The constant tracks
        # the SEED, so it only moves when properties.0002 does or when legacy
        # gains/loses a VillaCountry row.
        expected_gap=-225,
        # GAP-108: counts unstamped rows on purpose (whole-table override of
        # the legacy-rows default) — the gap is defined against the whole
        # seeded table, not the legacy slice — but never the XX sentinel.
        loaded_count=lambda m: m._default_manager.exclude(iso2="XX").count(),
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
    # (retired in place, never skipped), and blank-name rows are skipped by the
    # loader (0 of them on ResProd, so the bare total matches).
    # GAP-108: the `unknown-xx` sentinel (stamped `UNKNOWN_LEGACY_ID`) is
    # excluded here, as it already is on the two slices below. It is minted
    # lazily by the first FK fallback — ResProd mints it for villa 570 — so
    # counting it made this check read -1 for a row that has no legacy twin by
    # construction. Staff-created rows stopped counting with the GAP-108
    # legacy-rows default.
    _Check(
        "SELECT COUNT(*) FROM VillaRegion",
        Region,
        "Region",
        loaded_count=lambda m: (
            m._default_manager.filter(legacy_id__isnull=False)
            .exclude(legacy_id=UNKNOWN_LEGACY_ID)
            .count()
        ),
    ),
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
        # Rows CurrencyLoader skips. ResProd 2026-09-15 (7 rows): the three
        # soft-deleted junk codes that are not 3-letter alphabetic — HTFG (4),
        # RUPEE (5), RS (7) — plus the soft-deleted EUR twin (2), since the
        # live EUR (3) claims the code first (BUG-028). Before BUG-028 the
        # fourth skip was the LIVE EUR, losing to its deleted twin.
        expected_gap=4,
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
        # GAP-108 value check, not a count (`get_solo()` auto-creates the
        # singleton, so a row count always passes): PropertyDefaultsLoader
        # applies the FIRST CPD row's `CurrencyId` onto the singleton. A gap
        # means the loader found no Currency under that id (skipped junk
        # row) and the singleton kept its old currency, or it never ran.
        # ResProd: 1 CPD row, CurrencyId 3 (the live EUR) ⇒ 3 = 3.
        "SELECT ISNULL((SELECT TOP 1 CurrencyId FROM VillaConfigPropertyDefault ORDER BY Id), 0)",
        PropertyDefaults,
        "PropertyDefaults currency legacy_id (CPD row)",
        expected_gap=0,
        loaded_count=_defaults_currency_legacy_id,
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
        f"WHERE {live_villa_sql('v.')} "
        # GAP-108: inactive mappings are filtered, as in the loader (262 on
        # ResProd; structural gap stays 0).
        f"AND {legacy_active_sql('m.')}"
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
        # GAP-108: no `DeletedAt` filter — ContactLoader reads every row and
        # loads a deleted contact as INACTIVE (0 deleted on ResProd, so no
        # gap moves).
        "SELECT COUNT(*) FROM VillaContact",
        Person,
        "Person (owner/agent)",
        # VillaContact owner/agent rows keep the bare legacy_id; GAP-045 D5-3
        # also lands VillaClientDetails customers in Person (keyed `client-{id}`),
        # so exclude every `client-` row here (the customer rows AND the
        # `unknown_client` sentinel) or they'd inflate the loaded count and turn
        # this check RED. The `client-` slice is checked separately below.
        # GAP-089: the spreadsheet importers' `sheet-` persons have no legacy
        # twin either. Organic persons (legacy_id NULL) never count.
        loaded_count=lambda m: (
            m._default_manager.filter(legacy_id__isnull=False)
            .exclude(legacy_id__startswith=CLIENT_LEGACY_PREFIX)
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
        # GAP-108: only stamped channels on stamped persons — a staff-added
        # channel, or any channel of an organic person, never counts.
        # Pinned on ResProd (13-Aug-2026): 319 legacy rows, 317 loaded. The 2
        # skips are the rows `ContactEmailLoader.transform` rejects for having
        # no `@` — Id 30 (empty string) and Id 270 (the literal `tbc`).
        expected_gap=2,
        loaded_count=lambda m: (
            m._default_manager.filter(legacy_id__isnull=False, contact__legacy_id__isnull=False)
            .exclude(contact__legacy_id__startswith=CLIENT_LEGACY_PREFIX)
            .exclude(contact__legacy_id__startswith=SHEET_LEGACY_PREFIX)
            .count()
        ),
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaContactTele",
        PersonPhone,
        "PersonPhone",
        # Same slice exclusions and legacy-only filters as PersonEmail above.
        # Pinned on ResProd (13-Aug-2026): 259 legacy rows, 251 loaded. The 8
        # skips are 7 blank numbers plus Id 221, whose `ContactId` matches no
        # VillaContact row, so it has no person to hang on.
        expected_gap=8,
        loaded_count=lambda m: (
            m._default_manager.filter(legacy_id__isnull=False, contact__legacy_id__isnull=False)
            .exclude(contact__legacy_id__startswith=CLIENT_LEGACY_PREFIX)
            .exclude(contact__legacy_id__startswith=SHEET_LEGACY_PREFIX)
            .count()
        ),
    ),
    _Check(
        # GAP-108 structural invariant (BUG-029's primary-flag flip passed
        # every count): an owner/agent Person with ≥1 loaded email has
        # exactly one primary among them. The partial unique constraint
        # already rules out two, so in practice this catches a contact with
        # no primary: ContactEmailLoader demotes a rival primary (ignoring
        # its own row, so a re-run is stable) but never promotes one; it
        # holds on ResProd only because the legacy flags are clean. Caveat: the
        # loader skips a blank / `@`-less email, so a contact whose legacy
        # primary is that junk row and who has other valid emails loads
        # with none — a real violation to itemise, not a false one. ResProd
        # 2026-09-15: 0 contacts lack an `IsPrimary` valid email or have two;
        # both invalid emails (Ids 30, 270) are their contact's only email.
        "SELECT 0",
        Person,
        "Person (owner/agent) primary email count != 1 (must be 0)",
        loaded_count=lambda m: (
            m._default_manager.filter(legacy_id__isnull=False)
            .exclude(legacy_id__startswith=CLIENT_LEGACY_PREFIX)
            .exclude(legacy_id__startswith=SHEET_LEGACY_PREFIX)
            .annotate(
                loaded_emails=Count("emails", filter=Q(emails__legacy_id__isnull=False)),
                loaded_primaries=Count(
                    "emails", filter=Q(emails__legacy_id__isnull=False, emails__is_primary=True)
                ),
            )
            .filter(loaded_emails__gt=0)
            .exclude(loaded_primaries=1)
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
        # Counts legacy_id NULL rows on purpose: `organisation_for_company_name`
        # never stamps one, so a staff-created agency does shift this gap.
        loaded_count=lambda m: (
            m._default_manager.filter(org_type=OrgType.AGENCY)
            .exclude(legacy_id__startswith=SHEET_LEGACY_PREFIX)
            .count()
        ),
    ),
    _Check(
        # GAP-108 structural invariant (BUG-030 §15): `_company_name` maps the
        # `COMPANY_PLACEHOLDERS` to no agency, so no Organisation may carry
        # one as its name. Every org type and source counts — agencies carry
        # no legacy_id, and a placeholder-named org is a defect whoever wrote
        # it. Postgres TRIM strips spaces only (Python `.strip()` also strips
        # tabs/newlines), the same caveat as the legacy side above.
        "SELECT 0",
        Organisation,
        "Organisation named NA / N/A / - (must be 0)",
        loaded_count=lambda m: (
            m._default_manager.annotate(normalised=Upper(Trim("name")))
            .filter(normalised__in=COMPANY_PLACEHOLDERS)
            .count()
        ),
    ),
    _Check(
        _LIVE_VILLAS_QUERY,
        Property,
        "Property",
        # Was 1 (the blank-Name villa, 249 on the 24-Apr dump) while the
        # legacy side counted it; GAP-108 moved the blank-name skip into
        # `live_villa_sql`, so both sides count the same villas. ResProd:
        # 387 live, 1 blank (543) ⇒ 386.
        expected_gap=0,
    ),
    # GAP-108: PropertyLoader writes these three satellites for every loaded
    # property (`_process_row`), so each is one row per loaded Property —
    # the same gap as Property (ResProd: 386 live named villas ⇒ 386). A gap
    # here that Property lacks is a satellite write that failed after the
    # property row saved. Loaded = satellites of legacy properties only.
    _Check(
        _LIVE_VILLAS_QUERY,
        PropertyLocation,
        "PropertyLocation",
        expected_gap=0,
        loaded_count=_one_per_loaded_property,
    ),
    _Check(
        _LIVE_VILLAS_QUERY,
        PropertyCapacity,
        "PropertyCapacity",
        expected_gap=0,
        loaded_count=_one_per_loaded_property,
    ),
    _Check(
        _LIVE_VILLAS_QUERY,
        PropertySettings,
        "PropertySettings",
        expected_gap=0,
        loaded_count=_one_per_loaded_property,
    ),
    _Check(
        # GAP-108: 0 to 7 rows per loaded villa (`_DESCRIPTION_QUERY`). ResProd
        # 2026-09-15: OVERVIEW 8 + HOUSE_RULES 12 + OTHER_INFORMATION 193 +
        # ROOMS 127 + FURTHER_INFO 1 + WEB_DESCRIPTION 361 + LOCATION 347 =
        # 1 049, equal to a Python `.strip()` replay of PropertyLoader's own
        # query ⇒ 0. Loaded = rows stamped `<VillaId>-<section>`; a staff-
        # written section (legacy_id NULL) never counts, but a legacy row a
        # staff edit later blanked still does (no stale-row sweep).
        _DESCRIPTION_QUERY,
        PropertyDescription,
        "PropertyDescription",
        expected_gap=0,
    ),
    _Check(
        # GAP-108 structural invariant: legacy `VillaMaster.Slug` holds the
        # WordPress URL (385 of 386 loaded villas on ResProd contain `://`);
        # `_property_slug` slugifies it. Guards that path and any later write
        # to an imported property's slug. Organic properties are out of scope.
        "SELECT 0",
        Property,
        "Property slug containing :// (must be 0)",
        loaded_count=lambda m: m._default_manager.filter(
            legacy_id__isnull=False, slug__contains="://"
        ).count(),
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaCollection WHERE DeletedAt IS NULL",
        Collection,
        "Collection",
    ),
    _Check(
        f"SELECT COUNT(*) FROM VillaCollectionsMappings WHERE {legacy_active_sql()}",
        CollectionMembership,
        "CollectionMembership",
        # BUG-030 §13 (24-Apr-2025 dump, before the GAP-108 `IsActive`
        # filter): 308 = 3 duplicate (collection, villa) pairs + 22
        # memberships on deleted villas + 283 live memberships of the five
        # collections deleted together on 2024-05-28, which CollectionLoader
        # drops (decision 2026-09-11: drop, record here).
        # GAP-108 on ResProd: 2 206 rows, of which 194 `IsActive = 0` and 921
        # NULL (= inactive) filtered → 1 091 active; loaded = 1 082 distinct
        # (villa, collection) pairs on a live collection + loaded villa ⇒ 9.
        expected_gap=9,
    ),
    _Check(
        f"SELECT COUNT(*) FROM VillaRooms WHERE {legacy_active_sql()}",
        Room,
        "Room",
        # Rooms whose VillaId points at a property that wasn't loaded
        # (soft-deleted or empty-Name VillaMaster) have no parent to attach to.
        # 307 on the 24-Apr dump. GAP-108 on ResProd: 2 714 rooms - 30
        # inactive = 2 684; 321 of those sit on an unloaded villa.
        expected_gap=321,
    ),
    _Check(
        f"SELECT COUNT(*) FROM VillaRooms WHERE PlacementId IS NOT NULL AND {legacy_active_sql()}",
        Room,
        "Room placement (GAP-065)",
        # No-loss gate: every legacy room with a placement must land with the
        # raw string preserved in `placement_note`. The gap has two
        # legitimate causes: (a) rooms whose parent property wasn't loaded
        # (the Room gap above, restricted to rows with a PlacementId);
        # (b) dangling PlacementId → NULL/blank
        # VillaRoomsPlacement.Name (the LEFT JOIN preserves the room but the
        # note is honestly empty).
        # `placement_note` is API-writable, so count only the legacy slice —
        # a staff-entered note during the cutover window must not shift the
        # gap.
        # GAP-108 on ResProd (active rooms only): 2 409 with a PlacementId;
        # 61 = (a) on an unloaded villa or (b) blank/dangling placement name.
        expected_gap=61,
        loaded_count=lambda m: (
            m._default_manager.exclude(placement_note="").filter(legacy_id__isnull=False).count()
        ),
    ),
    _Check(
        # GAP-108: RoomLoader writes one RoomBeds per room it loads. Unlike
        # the Room check the legacy side is restricted to loaded villas, so
        # the structural gap is 0. ResProd: 2 684 active rooms - 321 on an
        # unloaded villa (the Room gap) = 2 363.
        "SELECT COUNT(*) FROM VillaRooms r "
        f"JOIN VillaMaster m ON m.Id = r.VillaId AND {live_villa_sql('m.')} "
        f"WHERE {legacy_active_sql('r.')}",
        RoomBeds,
        "RoomBeds",
        expected_gap=0,
        loaded_count=lambda m: m._default_manager.filter(room__legacy_id__isnull=False).count(),
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaPropertyImages",
        PropertyImage,
        "PropertyImage",
        # Images for an unloaded parent property, or rows with an empty filename.
        # Pinned on ResProd (13-Aug-2026): 19 071 legacy rows, 18 232 loaded.
        # All 839 skips sit on the 35 soft-deleted villas `live_villa_sql`
        # excludes — 0 are empty filenames and 0 are on a live villa, so no
        # loaded property loses an image.
        expected_gap=839,
    ),
    _Check(
        f"SELECT COUNT(*) FROM VillaNearBy WHERE {legacy_active_sql()}",
        PropertyNearbyPlace,
        "PropertyNearbyPlace",
        # Parent property unresolved, place type unresolved, or empty name.
        # 77 on the 24-Apr dump. GAP-108 on ResProd: 178 - 1 inactive = 177;
        # 78 of those hit one of the three skips.
        expected_gap=78,
    ),
    _Check(
        # GAP-110: a RatePlan is one (villa, currency) regime, not a season,
        # so both sides count VILLAS. Legacy = live villas with ≥1 live priced
        # rate row (the loaders' shared predicate, so rate-less seasons drop
        # out of both sides). Loaded = distinct villas owning a `villa:`-keyed
        # regime plan that actually carries ≥1 legacy period (a plan the band
        # loader couldn't populate is not a loaded villa; staff-created plans
        # never count). Gap = villas the loader couldn't resolve (no Property,
        # no currency) or whose plan got no legacy period — structurally ≥ 0.
        # The pre-regroup numbers (710 seasons → 521 plans, gap 67) no longer
        # apply. ResProd 2026-09-15: 346 legacy villas; each is a loaded
        # Property (same `live_villa_sql`) and `resolve_season_currency`
        # always ends at the default currency, so 0 unless a regime's bands
        # all fail to load.
        "SELECT COUNT(DISTINCT s.VillaId) FROM VillaSeason s "
        f"JOIN VillaMaster m ON m.Id = s.VillaId AND {live_villa_sql('m.')} "
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
        # SMELL-021: the loader stamps GROSS on every imported plan. Not
        # because legacy lacks a NET signal — it has one: `PriceType` 10 = Net
        # (`Enums.cs:153`) on 2 083 live VillaSeasonRate rows on ResProd
        # (2026-09-15; 1 887 non-extra on 10 loaded villas, 57 in the priced
        # universe) — but because the legacy quote path adds the rate row's
        # `WeeklyPrice / 7` verbatim per night whatever `PriceType` says
        # (`ResService.cs:1225-1237`), so GROSS reproduces what legacy
        # charged. Legacy side is a constant 0; any imported plan carrying NET
        # means the stamp regressed to the model default (or was hand-edited
        # under a legacy_id) — a BLOCKER.
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
        # GAP-037 / GAP-108: RatePlanLoader bands each season's non-blank
        # `Inclusion` as one PropertyService (`season:<ID>:svc`) when the
        # season is live, on a loaded villa, carries ≥1 priced rate row (else
        # it mints no plan) and has a live, non-inverted VillaSeasonDates
        # window (`_live_window` compares dates). Shifters: a group whose
        # savepoint errors, and whitespace-only (non-space) Inclusion (see
        # `_non_blank_sql`). ResProd 2026-09-15: 994 live seasons with an
        # Inclusion, 948 pass every filter.
        "SELECT COUNT(*) FROM VillaSeason s "
        f"JOIN VillaMaster m ON m.Id = s.VillaId AND {live_villa_sql('m.')} "
        f"WHERE s.DeletedAt IS NULL AND {_non_blank_sql('s.Inclusion')} "
        "AND EXISTS (SELECT 1 FROM VillaSeasonRate r "
        f"WHERE r.SeasonId = s.ID AND {PRICED_ROW_PREDICATE}) "
        "AND (SELECT CAST(MIN(d.FromDate) AS date) FROM VillaSeasonDates d "
        "WHERE d.SeasonId = s.ID AND d.DeletedAt IS NULL) "
        "<= (SELECT CAST(MAX(d.ToDate) AS date) FROM VillaSeasonDates d "
        "WHERE d.SeasonId = s.ID AND d.DeletedAt IS NULL)",
        PropertyService,
        "PropertyService",
        expected_gap=0,
    ),
    _Check(
        # BUG-013: RateBand has two legacy sources — parent VillaSeasonRate rows
        # (→ simple / base-weekly fallback rules) AND child VillaOccupencyPrice
        # bands on occupancy-flagged parents (→ one band rule each).
        # GAP-108 REPLACED this query. It used to count every non-extra,
        # non-deleted VillaSeasonRate row whatever its price or season, which on
        # ResProd is 39 868 against 6 633 loaded — a gap of 33 235 that is 28 721
        # priceless rows plus rows on deleted seasons and villas, i.e. rows no
        # loader ever looks at and legacy itself cannot quote (BUG-028: both
        # ResProd quote procs require a NightlyPrice). Counting them measured
        # nothing and buried the terms that do move. The query now counts the
        # loader's actual source universe (`_RB_SRC`), which is set-equal to it:
        # replaying the pipeline, every one of the 7 095 rows ends up either
        # loaded or shadowed, and nothing else reaches the flattener.
        # `ISNULL(r.IsOccupationPrice, 0)`: the flag is nullable in the ResProd
        # schema, and a bare `NOT (r.IsOccupationPrice = 1 AND ...)` evaluates
        # UNKNOWN on a NULL, dropping the row from BOTH subqueries while the
        # loader (a falsy `parent.get(...)`) loads it as a base-weekly row.
        _rate_band_source_sql(),
        RateBand,
        "RateBand",
        # Pinned on ResProd (13-Aug-2026) by replaying the loader's own pipeline;
        # zero residual. Legacy 7 095 = 6 398 non-occupancy parents + 697 valid
        # occupancy children (302 parents replaced). Loaded 6 633. Itemised:
        #   + 495  flattener-shadowed sources — a band that won no (date x party)
        #          cell because a higher-precedence sibling on the same regime
        #          plan covered it whole (481 parents + 14 occupancy children)
        #   -   8  synthetic `occ-fb-*` gap fallbacks the occupancy expansion
        #          adds for a party range the villa's own bands leave uncovered
        #   -  25  `#seg` fragments the flattener adds when one source survives
        #          in more than one flat cell
        #   = 462
        # Cross-checks: 7 095 - 495 = 6 600 loaded sources; + 8 = 6 608, the
        # loader's `created`; + 25 = 6 633 rows.
        # NOT terms, so don't hunt for them: the loader's `skipped` (16 seasons
        # with no regime plan + 293 synthetic fallbacks emptied by the property's
        # capacity) counts rows this universe never contained; `party_clipped`
        # narrows a bracket without dropping a band. Zero on this dump but each
        # would move the constant: resolver `dropped`, flattener `invalid_spans`
        # (which `_load_rows` does not currently surface — a source lost there
        # would break this identity silently), and `_row_to_band` rejections.
        expected_gap=462,
    ),
    _Check(
        # GAP-114: carried (copied-forward, owner-unconfirmed) rates survive as
        # `RateBand.is_indicative`. Legacy side = the RateBand universe above
        # narrowed to rows on a `CarriedRates` season; loaded side = imported
        # indicative bands (a staff carry-forward has no legacy_id). The gap is
        # the RateBand gap's pipeline terms restricted to carried sources.
        _rate_band_source_sql(CARRIED_RATES_PREDICATE),
        RateBand,
        "RateBand indicative (CarriedRates)",
        # Pinned on ResProd (16-Sep-2026) by replaying the loader's pipeline
        # (same replay as the RateBand check); zero residual. Legacy 1 616 =
        # 1 465 non-occupancy parents + 151 valid occupancy children on the 198
        # flagged seasons. Loaded 1 421. Itemised:
        #   + 218  flattener-shadowed carried sources (206 parents + 12
        #          occupancy children) — of the RateBand check's 495
        #   -   2  synthetic `occ-fb-*` fallbacks minted under a carried parent
        #          (of 8; a `dict(parent)` copy inherits the flag)
        #   -  21  `#seg` fragments of carried sources (of 25 — the copied-
        #          forward grids are where sibling seasons overlap most)
        #   = 195
        # Cross-checks: 1 616 - 218 = 1 398 loaded carried sources; + 2 + 21 =
        # 1 421 indicative rows. The 57 carried rows `_row_to_band` rejects
        # (of 293) are capacity-emptied fallbacks, outside this universe.
        expected_gap=195,
        loaded_count=lambda m: m._default_manager.filter(
            legacy_id__isnull=False, is_indicative=True
        ).count(),
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
        # PropertyLoader's villa filter (`live_villa_sql`: live + non-blank
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
        f"AND {live_villa_sql('m.')}",
        Extra,
        "Extra",
        expected_gap=0,
        loaded_count=lambda m: m._default_manager.filter(
            legacy_id__isnull=False, is_active=True
        ).count(),
    ),
    _Check(
        # PropertyContactAssignmentLoader writes one row per (mapping, role)
        # — legacy_id `<MappingId>-<RoleId or 0>` over its LEFT JOIN — so both
        # sides count those composites (the legacy side counted bare mappings
        # before GAP-108, and the old "composite collapse" reason was wrong:
        # the 24-Apr gap of 1 was the mapping on blank-name villa 249). Gap =
        # composites whose villa or contact did not load. ResProd 2026-09-15:
        # 466 mappings (23 role-less, 435 with one role, 8 with two) → 474
        # composites, 0 duplicates; 6 sit on soft-deleted villas 462 (3) and
        # 505 (2) (test villas) and 510 (1, Neradou); every mapped contact
        # has a name; blank-name villa 543 has no mapping ⇒ 6.
        "SELECT COUNT(DISTINCT CONCAT(m.Id, '-', ISNULL(r.RoleId, 0))) "
        "FROM VillaContactMapping m "
        "LEFT JOIN VillaContactRoleMapping r ON r.VillaContactMappingId = m.Id",
        PropertyContactAssignment,
        "PropertyContactAssignment",
        expected_gap=6,
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaClientDetails",
        Person,
        "Person (client)",
        # GAP-045 D5-3: VillaClientDetails now loads to Person directly (keyed
        # `client-{id}`), not Guest. Count only that slice, excluding the
        # `unknown_client` sentinel (minted only when a downstream row references
        # a skipped client — its presence must not move this count).
        # Pinned on ResProd (13-Aug-2026): 1 215 legacy rows, 1 031 loaded. The
        # gap is the rows that name nobody on EITHER side — only 111 clients
        # carry their own name, and GAP-108 U8b borrows the name of the lowest-Id
        # named live enquiry reached through the client's quotations for 920 more
        # (from ~Nov-2025 the legacy app stopped writing a name onto the client
        # row). The remaining 184 have no name anywhere to take: test accounts,
        # `info@`-style shared addresses and rows whose quotations reach no named
        # enquiry. `ClientLoader.transform` returns None for them rather than
        # minting a nameless Person.
        expected_gap=184,
        loaded_count=lambda m: (
            m._default_manager.filter(legacy_id__startswith=CLIENT_LEGACY_PREFIX)
            .exclude(legacy_id=UNKNOWN_CLIENT_LEGACY_ID)
            .count()
        ),
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaEnquire WHERE DeletedAt IS NULL",
        Enquiry,
        "Enquiry",
        # Negative gap: loaded > legacy. Synthesised enquiries created to
        # satisfy the now-mandatory Quotation.enquiry FK for legacy quotations
        # that carried no enquiry of their own (no booking-synth quotations
        # since GAP-108 unregistered the booking loaders). -8 on the 24-Apr dump
        # included 3 BookingLoader.ensure_enquiry rows, hence -5.
        # GAP-108 on ResProd: 87 soft-deleted enquiries filtered on both
        # sides; every live quotation's EnquireId is a live enquiry (0 with
        # EnquireId 0/NULL/missing/deleted), so no stand-ins ⇒ 0.
        expected_gap=0,
        # GAP-089: `import_enquiry_sheet` adds ~2.4k historic `sheet-enquiry-`
        # rows with no VillaEnquire twin — leave them out of the comparison,
        # along with organic (legacy_id NULL) enquiries.
        loaded_count=lambda m: (
            m._default_manager.filter(legacy_id__isnull=False)
            .exclude(legacy_id__startswith=SHEET_LEGACY_PREFIX)
            .count()
        ),
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaFinance WHERE VillaId IS NOT NULL",
        PropertyFinance,
        "PropertyFinance",
        # 1239 = legacy rows the per-villa pass does not port. Pinned on
        # ResProd (13-Aug-2026); zero residual:
        #   1597  `VillaId IS NOT NULL` (= every row; the column is NOT NULL)
        #  - 413  `VillaId = 0`, `ParentId` NULL: contact-default templates
        #  - 676  `VillaId = 0`, `ParentId` set: parent-child overrides with
        #         no villa of their own
        #  - 150  `VillaId > 0` on a villa `live_villa_sql` excludes
        #         (soft-deleted or blank-named)
        #  =  358  stamped per-villa rows (override rows with `VillaId > 0`
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
        expected_gap=1239,
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
        # Pinned on ResProd (13-Aug-2026): 1 550 = 1 550. It was 9 until GAP-108
        # U8b — the 9 quotations with `ClientDetailsId` 0 used to be dropped for
        # want of a customer and now resolve one through their enquiry.
        expected_gap=0,
    ),
    _Check(
        # GAP-112: `EnquiryLoader` cannot link the people the sheet imports mint
        # later, so their quotations load on the sentinel; the
        # `relink_enquiry_customers` cutover step moves them. Non-zero means that
        # step was skipped (268 on the run-5 DB). The ambiguous and unresolvable
        # remainder (53 on run 5) is deliberately not pinned: it depends on the
        # sheet contents and moves with §6g hand-merges.
        "SELECT 0",
        Quotation,
        "Quotation on unknown client with a relinkable enquiry (must be 0)",
        loaded_count=_relinkable_sentinel_quotations,
    ),
    _Check(
        "SELECT COUNT(*) FROM VillaQuotationDetails",
        QuotationLine,
        "QuotationLine",
        # Was -2 (lines on the booking-synth quotations, gone since GAP-108).
        # Pinned on ResProd (13-Aug-2026): 8 035 legacy rows, 7 690 loaded.
        # Every one of the 345 is the single FK-resolution skip in `transform`
        # (`quotation is None or prop is None`); zero residual:
        #   206  line on a soft-deleted VillaQuotationMaster, which
        #        `QuotationLoader` never loads
        #    79  orphan line whose `QuotationMasterId` matches no master row at
        #        all (173 distinct dangling ids; legacy has no FK here)
        #    53  line on a LIVE loaded quote pointing at a villa that does not
        #        load — all of them villa 462 or 505, the two deleted test
        #        villas, so no real villa loses a line
        #     7  line with `VillaId` 0/NULL, so nothing to price against
        # No line is lost to dates or currency any more: after GAP-108 U8b fills
        # a missing stay date from the master, both date guards and the currency
        # guard fire 0 times.
        expected_gap=345,
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
        # Pinned on ResProd (13-Aug-2026): 836 legacy rows, 635 loaded. Every
        # skip is a collapse onto the `unique_person_preference` triple
        # (person, preference_type, quotation) or a dangling FK; zero residual:
        #   149  exact duplicate legacy rows — same client, type AND quotation;
        #        the legacy table has no unique constraint and its screen
        #        re-saves (one client wrote the same VIP note 25 times)
        #    38  different unloaded client ids collapsing onto the one
        #        unknown-client sentinel, all with quotation=NULL (legacy's
        #        hard-coded placeholder id 1 and test accounts)
        #    12  same client, two DIFFERENT unresolved quotations, both
        #        flattened to quotation=NULL and so merged (3 of them belong to
        #        a real named customer; the rest to a dangling client id)
        #     2  dangling ClientPrefMasterId 12 and 13 — VillaClientPrefMaster
        #        has 11 rows, max Id 11
        # Order-independent (skips = rows - distinct triples), so the constant
        # holds even though `legacy_query` has no ORDER BY. U8d's quotation
        # fallback re-keys 474 of those triples onto a real person without
        # moving this number: the two sentinel buckets above are exactly the
        # rows it cannot help (quotation=NULL, so there is nobody to borrow).
        # The loader's
        # `data_migration.preference_quotation_unresolved` count (47 here) is a
        # CAUSE spread across these buckets, not a bucket: 9 of the 47 load with
        # quotation=NULL, 38 are among the skips.
        expected_gap=201,
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
        #              = days trimmed under bookings / unreleased holds that
        #                exist when the loader runs (it logs `trimmed_days`)
        #              + days on unloaded properties (logged as skips)
        #              + days of runs that errored (`report.errors`).
        # No legacy booking loads any more (GAP-108) and the sheet importers
        # run after `loadlegacy`, so on a fresh DB the first term is 0.
        # ResProd 2026-09-15: 10 258 future blocking days, 0 of them on a
        # villa outside `live_villa_sql` ⇒ 0.
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
            blockers += self._archive_stay_section(cursor)
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
            loaded_count = check.count_loaded()
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

    def _archive_stay_section(self, cursor: Any) -> list[str]:
        """GAP-113: classify the live `VillaArchiveBookings` stays against the
        loaded PastStays, as `import_archive_stays` does. Any stay still to
        `enrich` or `create` blocks, as does a live row that cannot even be
        parsed: that stay is missing from its guest's history. Either the import
        was skipped, or it reported the stay (`person_ambiguous` /
        `person_inactive` / a row error) and nobody resolved it — fix the data,
        or land it by hand: a create as `archive-stay-<Id>`, an enrich onto its
        sheet stay (CUTOVER.md §5). The skip
        categories depend on the sheet, so they are shown, never pinned."""
        cursor.execute(ARCHIVE_ROWS_SQL)
        grouped = group_rows(list(rows_as_dicts(cursor)))
        results = classify(grouped.stays)
        by_category: dict[str, list[str]] = {}
        if grouped.test_row_ids:
            by_category["test_row"] = [str(i) for i in grouped.test_row_ids]
        for result in results:
            ids = "/".join(str(i) for i in result.stay.member_ids)
            by_category.setdefault(result.category, []).append(ids)
        self.stdout.write(
            "\nArchive stays (VillaArchiveBookings → PastStay, import_archive_stays):"
        )
        pending = {"enrich", "create"}
        self.stdout.write(
            render_table(
                ("category", "stays", "status"),
                [
                    (category, len(ids), "BLOCKER" if category in pending else "OK")
                    for category, ids in sorted(by_category.items())
                ]
                or [("-", 0, "OK")],
            )
        )
        blockers = [
            f"Archive stays to {category} (import_archive_stays): {len(stays)} — "
            + ", ".join(stays[:10])
            + (f", +{len(stays) - 10} more" if len(stays) > 10 else "")
            for category in sorted(pending)
            if (stays := by_category.get(category))
        ]
        if grouped.errors:
            blockers.append(
                "Archive rows that cannot land (import_archive_stays): "
                + ", ".join(f"{legacy_id} {message}" for legacy_id, message in grouped.errors)
            )
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
                # Defensive: a dry-run dump may predate VillaSyncDetails. This
                # section is informational, so degrade to "n/a" rather than
                # aborting the whole reconcile.
                rows.append((label, f"n/a ({type(exc).__name__})", "INFO"))

        _count(
            "VillaBooking.BookingUrl",
            "SELECT COUNT(*) FROM VillaBooking "
            "WHERE BookingUrl IS NOT NULL AND LTRIM(RTRIM(BookingUrl)) <> ''",
        )
        # ResProd names the table `VillaSyncDetails` (the repo's EF entity is
        # the singular `VillaSyncDetail`): 5 773 rows over 2 sites, 2026-09-15.
        _count("VillaSyncDetails (rows)", "SELECT COUNT(*) FROM VillaSyncDetails")
        _count(
            "VillaSyncDetails (sites)",
            "SELECT COUNT(DISTINCT SiteId) FROM VillaSyncDetails",
        )

        header = ("wordpress source", "legacy count", "status")
        self.stdout.write("\n\nWordPress external-ID surface (informational — loader not built):\n")
        self.stdout.write(render_table(header, rows))
