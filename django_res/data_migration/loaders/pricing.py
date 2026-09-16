"""Pricing: VillaSeason -> RatePlan; VillaSeasonRate -> RatePeriod + RateBand.

Legacy structure:
  VillaSeason (id, name, villa_id, notes, inclusion)
    └── VillaSeasonDates (id, season_id, from_date, to_date)
    └── VillaSeasonRate (id, season_id, villa_id, currency_id, from_date,
                        to_date, party_size, price_type, weekly_price,
                        nightly_price, is_poa, ...)

New structure (GAP-056):
  RatePlan (property, currency, price_basis)  — date-less regime bucket (GAP-110)
    └── RatePeriod (plan, date_from, date_to)  — disjoint date axis
          └── RateBand (period, min_party, max_party, nightly, weekly, is_poa)

Strategy:
- One RatePlan per (villa, currency) — GAP-110: every live, priced season of a
  villa that resolves to the same currency merges onto one regime plan keyed
  `villa:<VillaId>:<CODE>`. Currency comes from the season's own
  non-NULL VillaSeasonRate rows (most recent first); a season with only
  NULL/0 CurrencyId rows falls back to the villa's other non-NULL rate rows,
  then settings → EUR — never `Currency.objects.first()` (GAP-014 step 0),
  and never `resolve_property_currency`, whose plans-first step reads the
  very table this loader populates (load-order dependent, and a wrong stamp
  would re-resolve from itself forever on idempotent re-runs).
- The RatePlan owns no rate rows directly: `RateBandLoader` builds the plan's
  disjoint `RatePeriod` date axis (via the shared `segment_card_rules`
  segmentation) and hangs each party band off its covering period.
- One VillaSeasonRate -> one RateBand per surviving fragment:
  `resolve_rate_band_overlaps` pre-normalises the legacy rows (junk filter,
  checkout-convention boundary trim); the conflict policy is the shared
  `pricing.services.flattening` grid flattener's — split, not clip, so an
  interior collision keeps both sides of the loser (BUG-016; legacy had no
  precedence concept — see "Rate rule overlap resolution" in
  data_migration/CUTOVER.md).
- Occupancy bands (BUG-013): a VillaSeasonRate flagged `IsOccupationPrice`
  carries child VillaOccupencyPrice rows (party-range → weekly price). The
  RateBand query LEFT JOINs them and `_prepare_occupancy_rows` expands a banded
  parent into one RateBand per band plus base-weekly fallbacks over the party
  gaps the bands don't cover, so a guest count matching no band still gets the
  legacy base-weekly quote.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import structlog
from django.db import transaction

from data_migration.base import BaseLoader, LoadReport
from pricing.models.currency import Currency
from pricing.models.rate import RateBand, RatePeriod, RatePlan
from pricing.services.currency import default_currency, settings_currency
from pricing.services.flattening import SourceBand, flatten_rate_grid
from pricing.services.intervals import Interval, intervals_overlap, subtract_intervals
from pricing.services.period_names import derive_period_name
from properties.enums import PriceBasis
from properties.models.property import Property
from properties.models.services import PropertyService

logger = structlog.get_logger(__name__)


def _to_decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    if hasattr(value, "date"):  # datetime -> date
        return value.date()
    return value


def _positive(v: Any) -> Decimal | None:
    """A price legacy can quote: 0.00 / negative / NULL are all "absent"."""
    d = _to_decimal(v)
    return d if d is not None and d > 0 else None


def _row_prices(row: dict[str, Any]) -> tuple[Decimal | None, Decimal | None, bool]:
    """(nightly, weekly, is_poa) of a VillaSeasonRate row, shared by the
    overlap resolver's pre-filter and `transform` so the skip predicate can't
    drift. BUG-028: only positive prices count, and `Price` is ignored —
    legacy quotes read NightlyPrice/WeeklyPrice (`RatesModel.Price` merely
    echoes WeeklyPrice), so a Price-only or 0.00 row was never quotable."""
    return (
        _positive(row.get("NightlyPrice")),
        _positive(row.get("WeeklyPrice")),
        bool(row.get("IsPOA")),
    )


def _has_price(row: dict[str, Any]) -> bool:
    nightly, weekly, is_poa = _row_prices(row)
    return bool(nightly or weekly or is_poa)


@dataclass(frozen=True)
class OverlapResolution:
    """Outcome of `resolve_rate_band_overlaps`: surviving rows + counters."""

    rows: list[dict[str, Any]]
    trimmed: int
    dropped: int


@dataclass
class _WorkRow:
    """Mutable working copy of one legacy row during pre-normalisation.

    `party_intervals` is the row's authoritative party coverage: inclusive
    `(low, high)` brackets, `high=None` meaning "up to property capacity" —
    treated as unbounded so the resolver stays pure (capacity is resolved
    later, in `_row_to_band`). The boundary trim is gated on party overlap
    across the whole set.
    """

    id: int
    row: dict[str, Any]
    orig_from: date
    date_from: date
    date_to: date
    party_intervals: list[Interval]
    disc: str


def _party_overlap(a: _WorkRow, b: _WorkRow) -> bool:
    return any(intervals_overlap(i, j) for i in a.party_intervals for j in b.party_intervals)


def resolve_rate_band_overlaps(rows: list[dict[str, Any]]) -> OverlapResolution:
    """Pre-normalise legacy VillaSeasonRate rows before loading.

    Legacy had no precedence concept (its per-night lookup was an unordered
    `TOP 1`), so overlapping rows are data noise to resolve, not behaviour to
    preserve. Policy (user-confirmed, see CUTOVER.md):

    Rows are grouped by the regime plan key the loader stamps on each row
    (`_plan_key`, GAP-110): seasons of one villa + currency share a plan, so
    their rows trim and resolve together; different villas never touch. A
    row without the stamp is a caller bug (KeyError), not a group of its own.

    1. Pre-filter rows `transform()` would skip (junk dates, no price and not
       POA) so they can neither trim nor be trimmed. Within a group, exact
       duplicates sharing a `_legacy_id` discriminator are dropped (keep the
       first) — unreachable off real SQL PKs, but dirty input must not reach
       the flattener's duplicate-precedence ValueError.
    2. Boundary trim: legacy stored checkout-style contiguous bands (the next
       row starts on the day the previous one ends) but the new model is
       inclusive on both ends — trim one day off the earlier row's end. A
       two-night row trimmed to a single day is KEPT (inclusive dates make a
       one-day period legitimate); dropping it would lose that night.
       Compares *original* FromDates (never modified), so chains trim cleanly
       and the pass is order-independent.
    3. Conflict resolution happens later, in `_load_rows`, via the shared
       `pricing.services.flattening` grid flattener (BUG-016) — after
       `_row_to_band`'s capacity clamp, so brackets are concrete.

    Pure function of the input row set — DB-free, and deterministic /
    order-independent for PK-unique input (the duplicate-disc dedupe is
    keep-first, so pathological same-disc rows with differing payloads would
    be input-order-dependent; real SQL PKs make that unreachable). One input
    row maps to zero or one output rows, legacy ID unchanged.
    """
    trimmed = dropped = 0

    groups: dict[Any, list[_WorkRow]] = defaultdict(list)
    seen_discs: dict[Any, set[str]] = defaultdict(set)
    for row in rows:
        date_from = _as_date(row.get("FromDate"))
        date_to = _as_date(row.get("ToDate"))
        if date_from is None or date_to is None or date_to <= date_from:
            continue
        if not _has_price(row):
            continue
        band = row.get("_occ_band")
        if band is not None:
            # Occupancy-band / gap-fallback rows carry an explicit party range.
            intervals: list[Interval] = [band]
        else:
            party = int(row.get("PartySize") or 0)
            intervals = [(party, party)] if party > 0 else [(1, None)]
        # Unique discriminator: a band's OccId can numerically collide with a
        # simple row's ID within a season; `_legacy_id` is unique per row.
        disc = str(row.get("_legacy_id") or row["ID"])
        group = row["_plan_key"]
        if disc in seen_discs[group]:
            dropped += 1
            continue
        seen_discs[group].add(disc)
        groups[group].append(
            _WorkRow(
                id=int(row["ID"]),
                row=row,
                orig_from=date_from,
                date_from=date_from,
                date_to=date_to,
                party_intervals=intervals,
                disc=disc,
            )
        )

    kept_all: list[_WorkRow] = []
    for items in groups.values():
        for item in items:
            if any(
                other is not item
                and _party_overlap(item, other)
                and other.orig_from == item.date_to
                for other in items
            ):
                item.date_to -= timedelta(days=1)
                trimmed += 1
            if item.date_to < item.date_from:
                dropped += 1
            else:
                kept_all.append(item)

    out_rows: list[dict[str, Any]] = []
    for item in sorted(kept_all, key=lambda it: (it.id, it.disc)):
        out = dict(item.row)
        out["FromDate"] = item.date_from
        out["ToDate"] = item.date_to
        out_rows.append(out)
    return OverlapResolution(rows=out_rows, trimmed=trimmed, dropped=dropped)


PLAN_LEGACY_PREFIX = "villa:"


def plan_legacy_id(villa_id: int | str | None, currency_code: str) -> str:
    """The `legacy_id` of the regime plan carrying a legacy villa's seasons in
    one currency (GAP-110): `villa:<VillaId>:<CODE>`. Shared with
    `RateBandLoader` so both loaders agree on the key without a lookup table."""
    return f"{PLAN_LEGACY_PREFIX}{villa_id}:{currency_code}"


# The legacy row universe every pricing loader and reconcile check agrees on:
# a live, non-extra `VillaSeasonRate` row (alias `r`) with a real span and a
# price — a positive parent price, POA, or an occupancy parent whose child
# bands carry the price (`_prepare_occupancy_rows` prices those from the
# child, never the parent). Negative parent prices are junk we don't model.
PRICED_ROW_PREDICATE = (
    "r.DeletedAt IS NULL AND r.IsExTra <> 1 AND r.FromDate < r.ToDate"
    " AND (r.NightlyPrice > 0 OR r.WeeklyPrice > 0 OR r.IsPOA = 1"
    " OR (r.IsOccupationPrice = 1 AND EXISTS (SELECT 1 FROM VillaOccupencyPrice o"
    "  WHERE o.VillaSeasonRateId = r.ID AND o.OccupencyPrice > 0)))"
)

# The T-SQL twin of the band-validity guard inside `_prepare_occupancy_rows`
# below (a `VillaOccupencyPrice` row aliased `o`): a child band is only a band
# if its party range is positive and ordered and it carries a real price.
# `reconcile_legacy`'s RateBand check counts the same source universe as this
# loader, so it imports this rather than restating it — keep the two in step,
# and if the Python guard changes, change this string in the same commit.
VALID_OCCUPANCY_BAND_PREDICATE = (
    "o.OccupencyFrom > 0 AND o.OccupencyTo >= o.OccupencyFrom AND o.OccupencyPrice > 0"
)

# The season-level currency inputs to `resolve_season_currency`, against a
# `VillaSeason` aliased `s`. `SEASON_CURRENCY_SUBSELECT`: the season's own most
# recent non-NULL/non-zero rate row. `VILLA_CURRENCY_SUBSELECT`: same across ALL
# the villa's seasons — the GAP-014 rule-1 inference for the 2023-era seasons
# whose rows are all NULL but whose villa later got real currencies. One
# definition so `RatePlanLoader` (which mints the plan) and `RateBandLoader`
# (which must find it) can never resolve a season differently.
SEASON_CURRENCY_SUBSELECT = (
    "(SELECT TOP 1 r1.CurrencyId FROM VillaSeasonRate r1 "
    " WHERE r1.SeasonId = s.ID AND r1.CurrencyId IS NOT NULL AND r1.CurrencyId <> 0 "
    " AND r1.DeletedAt IS NULL ORDER BY r1.ID DESC)"
)
VILLA_CURRENCY_SUBSELECT = (
    "(SELECT TOP 1 r2.CurrencyId FROM VillaSeasonRate r2 "
    " WHERE r2.VillaId = s.VillaId AND r2.CurrencyId IS NOT NULL AND r2.CurrencyId <> 0 "
    " AND r2.DeletedAt IS NULL ORDER BY r2.ID DESC)"
)


def _season_label(row: dict[str, Any]) -> str:
    return str(row.get("Name") or f"Season {row['ID']}")


def _live_window(row: dict[str, Any]) -> tuple[date, date] | None:
    """A season's live `VillaSeasonDates` envelope, or None when it has no
    live rows or the stored window is inverted (junk — it would trip the
    `PropertyService` from<=to CHECK and roll back the whole plan)."""
    date_from = _as_date(row.get("DateFrom"))
    date_to = _as_date(row.get("DateTo"))
    if date_from is None or date_to is None or date_from > date_to:
        return None
    return date_from, date_to


def resolve_season_currency(row: dict[str, Any], prop: Property) -> Currency | None:
    """GAP-014 step 0: a season's currency from its own non-NULL rate rows
    (`CurrencyId`), else the villa's other rows (`VillaCurrencyId`), else the
    canonical settings → EUR chain.

    Never `Currency.objects.first()` (ordering-dependent) and never
    `resolve_property_currency`, whose plans-first step reads the very table
    `RatePlanLoader` populates — a mis-stamped currency could never
    self-correct on an idempotent re-run.
    """
    currency = Currency.objects.filter(legacy_id=str(row.get("CurrencyId") or "")).first()
    if currency is None:
        currency = Currency.objects.filter(legacy_id=str(row.get("VillaCurrencyId") or "")).first()
    if currency is None:
        currency = settings_currency(prop) or default_currency()
    return currency


class RatePlanLoader(BaseLoader):
    """VillaSeason -> RatePlan, one plan per (villa, resolved currency).

    GAP-110: legacy seasons are year/era buckets whose `VillaSeasonDates` were
    a data-entry helper, never a pricing input. A RatePlan is a dateless
    regime bucket (property, currency, price basis), so every live, priced
    season of a villa that resolves to the same currency is merged onto one
    plan keyed `villa:<VillaId>:<CODE>`; the seasons' rate rows become that
    plan's `RatePeriod` axis in `RateBandLoader`. Merged seasons stay
    traceable in `notes`. The plan owns no rate rows here.

    `_load_rows` additionally materialises each season's free-text Inclusion
    as a date-banded `PropertyService` (GAP-037), keyed `season:<ID>:svc` and
    dated by that season's live window.
    """

    name = "rate_plan"
    target_model = RatePlan
    legacy_pk_column = "ID"
    # CurrencyId / VillaCurrencyId: the season- and villa-level currency
    # inputs (shared subselects). RateCount: live, priced, non-extra rate rows
    # (shared predicate) — a season with none is not a regime and mints no
    # plan (the loader records a skip).
    # DateFrom/DateTo: the season's LIVE window (soft-deleted date rows are a
    # legacy "delete the season" side effect and must not band a service).
    legacy_query = (
        "SELECT s.ID, s.Name, s.VillaId, s.Notes, s.Inclusion, "
        f"{SEASON_CURRENCY_SUBSELECT} AS CurrencyId, "
        f"{VILLA_CURRENCY_SUBSELECT} AS VillaCurrencyId, "
        "(SELECT COUNT(*) FROM VillaSeasonRate r "
        f" WHERE r.SeasonId = s.ID AND {PRICED_ROW_PREDICATE}) AS RateCount, "
        "(SELECT MIN(d.FromDate) FROM VillaSeasonDates d "
        " WHERE d.SeasonId = s.ID AND d.DeletedAt IS NULL) AS DateFrom, "
        "(SELECT MAX(d.ToDate) FROM VillaSeasonDates d "
        " WHERE d.SeasonId = s.ID AND d.DeletedAt IS NULL) AS DateTo "
        "FROM VillaSeason s "
        "JOIN VillaMaster m ON m.Id = s.VillaId AND m.DeletedAt IS NULL "
        "WHERE s.DeletedAt IS NULL"
    )

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        """Group the season rows by (villa, resolved currency), then upsert one
        plan per group inside its own savepoint — one bad group can't abort
        the rest, the same isolation `BaseLoader._load_rows` gives a row."""
        groups: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        keys: dict[tuple[int, int], tuple[Property, Currency]] = {}
        prop_cache: dict[str, Property | None] = {}
        for row in rows:
            if row.get(self.legacy_pk_column) is None:
                report.skipped += 1
                continue
            villa_id = str(row.get("VillaId") or "")
            if villa_id not in prop_cache:
                prop_cache[villa_id] = Property.objects.filter(legacy_id=villa_id).first()
            prop = prop_cache[villa_id]
            if prop is None or not (row.get("RateCount") or 0):
                report.skipped += 1
                continue
            currency = resolve_season_currency(row, prop)
            if currency is None:
                report.skipped += 1
                continue
            key = (prop.pk, currency.pk)
            keys[key] = (prop, currency)
            groups[key].append(row)

        with transaction.atomic():
            # Own the legacy footprint: plans (and their inclusion services)
            # written under the pre-GAP-110 season-keyed ids would otherwise
            # survive an in-place re-run as a second active plan per regime.
            # Cascades the stale plans' legacy periods/bands; `RateBandLoader`
            # rebuilds those on the regime plans anyway.
            RatePlan.objects.filter(legacy_id__isnull=False).exclude(
                legacy_id__startswith=PLAN_LEGACY_PREFIX
            ).delete()
            PropertyService.objects.filter(
                legacy_id__isnull=False, legacy_id__endswith=":svc"
            ).exclude(legacy_id__startswith="season:").delete()
            for key, season_rows in groups.items():
                prop, currency = keys[key]
                try:
                    with transaction.atomic():
                        created = self._load_group(prop, currency, season_rows)
                except Exception as exc:  # isolate one bad group from the rest
                    report.errors.append((plan_legacy_id(prop.legacy_id, currency.code), repr(exc)))
                    continue
                # Counted only once the savepoint has committed — a rolled-back
                # group is an error, not a created plan.
                if created:
                    report.created += 1
                else:
                    report.updated += 1

    def _load_group(
        self,
        prop: Property,
        currency: Currency,
        season_rows: list[dict[str, Any]],
    ) -> bool:
        """Upsert the group's regime plan + inclusion services; True if the
        plan was created (False when updated in place)."""
        season_rows = sorted(season_rows, key=lambda r: int(r["ID"]))
        if len(season_rows) == 1:
            name = _season_label(season_rows[0])
            notes = str(season_rows[0].get("Notes") or "").strip()
        else:
            name = f"{currency.code} rates"
            lines = ["Merged legacy seasons:"]
            lines += [f"- {r['ID']} — {_season_label(r)}" for r in season_rows]
            for r in season_rows:
                blurb = str(r.get("Notes") or "").strip()
                if blurb:
                    lines.append(f"{_season_label(r)}: {blurb}")
            notes = "\n".join(lines)
        _, created = RatePlan.objects.update_or_create(
            legacy_id=plan_legacy_id(prop.legacy_id, currency.code),
            defaults={
                "property": prop,
                "name": name[:128],
                "currency": currency,
                "is_active": True,
                "notes": notes,
                # SMELL-021: stamped explicitly, not left to the model default.
                # Legacy DOES carry a Net signal (`VillaSeasonRate.PriceType` 10 =
                # Net: 2 083 live rows on ResProd, 2026-09-15; `RatesModel.Calculate()`
                # does branch on it), but the quote path adds the rate row's
                # `WeeklyPrice / 7` verbatim per night (`ResService.cs:1225-1237`),
                # never `GrossPrice` — so GROSS reproduces what legacy charged.
                # `reconcile_legacy` pins the invariant (zero non-GROSS legacy plans).
                "price_basis": PriceBasis.GROSS,
            },
        )
        # GAP-037: a season's free-text Inclusion becomes one date-banded
        # PropertyService on the villa, dated by the season's live window
        # (the plan no longer has one). No live window → nothing to band it on.
        for r in season_rows:
            inclusion = str(r.get("Inclusion") or "").strip()
            window = _live_window(r)
            if not inclusion or window is None:
                continue
            PropertyService.objects.update_or_create(
                legacy_id=f"season:{r['ID']}:svc",
                defaults={
                    "property": prop,
                    "name": "Included services",
                    "copy": inclusion,
                    "applies_from": window[0],
                    "applies_to": window[1],
                    "is_active": True,
                },
            )
        return bool(created)


def _party_gaps(bands: list[Interval]) -> list[Interval]:
    """Inclusive party ranges NOT covered by any band — the complement of the
    bands over ``[1, ∞)``, as disjoint brackets in ascending order (the shared
    `subtract_intervals` over the whole range). Because bands have finite
    highs, the result always ends in an open-topped gap (``high=None``);
    `transform` clamps that to the property capacity (a fully-covered range
    yields a gap whose low exceeds capacity, which `transform` then drops)."""
    return subtract_intervals([(1, None)], bands)


def _prepare_occupancy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand a VillaSeasonRate x VillaOccupencyPrice LEFT JOIN into the flat
    row set the resolver + `transform` consume (BUG-013).

    Each input row is one parent VillaSeasonRate optionally joined to one child
    band (`OccId`/`OccupencyFrom`/`OccupencyTo`/`OccupencyPrice`; all None when
    the parent has no matching child). Rows for one parent share an `ID`.

    - A parent NOT flagged `IsOccupationPrice`, or with NO valid occupancy child,
      passes through unchanged — the normal base-weekly (simple) path. Gating on
      the flag matches legacy (which only reads bands for occupancy rates) and
      ignores stray/orphan child rows on a non-occupancy parent. A childless
      occupancy parent likewise yields one OccId-null row → base-weekly.
    - A flagged parent with ≥1 valid child (`OccupencyFrom`/`To` both > 0,
      From ≤ To, and a non-zero `OccupencyPrice`) is replaced by: one **band
      row** per valid child (its own party range + `OccupencyPrice` as the
      weekly rate, `_legacy_id="occ-{OccId}"`) PLUS one **fallback row** per
      party gap the bands leave uncovered (the parent's base price,
      `_legacy_id="occ-fb-{parent}-{k}"`), so a guest count matching no band
      still gets the legacy base-weekly quote.
    - Invalid children (null/≤0 bound, From > To, null/0 price) are dropped, not
      coerced — a null bound would `None <= int` crash the resolver, and a
      priced-nobody band would otherwise leave a coverage hole. Legacy treats
      such a band as matching nobody, so the gap fallback covers that party
      range instead (parity, no hole).

    Pure function; band rows set `WeeklyPrice=OccupencyPrice` and leave
    `NightlyPrice` unset (the engine's `rule_nightly` derives it identically),
    never POA.
    """
    by_parent: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    order: list[Any] = []
    for row in rows:
        pid = row.get("ID")
        if pid not in by_parent:
            order.append(pid)
        by_parent[pid].append(row)

    out: list[dict[str, Any]] = []
    for pid in order:
        group = by_parent[pid]
        parent = group[0]
        bands: list[tuple[int, int, Decimal, Any]] = []
        if parent.get("IsOccupationPrice"):
            for row in group:
                occ_id = row.get("OccId")
                if occ_id is None:
                    continue
                frm, to = row.get("OccupencyFrom"), row.get("OccupencyTo")
                if frm is None or to is None:
                    continue
                frm, to = int(frm), int(to)
                # Keep in step with `VALID_OCCUPANCY_BAND_PREDICATE` above,
                # which reconcile_legacy uses to count this same universe.
                if frm <= 0 or to <= 0 or frm > to:
                    continue
                price = _positive(row.get("OccupencyPrice"))
                if price is None:
                    # A null/zero-price band prices nobody in legacy; dropping it
                    # lets the base-weekly fallback cover its party range rather
                    # than leaving a hole (no rule at all).
                    continue
                bands.append((frm, to, price, occ_id))

        if not bands:
            # Not an occupancy rate (or no valid children) → a plain base-weekly
            # rate row (the LEFT JOIN emits one such row even for orphan children).
            out.append(parent)
            continue

        for frm, to, price, occ_id in bands:
            band = dict(parent)
            band["ID"] = occ_id
            band["_legacy_id"] = f"occ-{occ_id}"
            band["_occ_band"] = (frm, to)
            band["WeeklyPrice"] = price
            # Nightly is derived from weekly by the engine (`rule_nightly`, same
            # HALF_EVEN round) — don't duplicate that here, and clear the
            # parent's nightly the copy inherited.
            band["NightlyPrice"] = None
            band["IsPOA"] = False
            out.append(band)

        gap_bands: list[Interval] = [(frm, to) for frm, to, _, _ in bands]
        for k, gap in enumerate(_party_gaps(gap_bands)):
            fallback = dict(parent)
            fallback["_legacy_id"] = f"occ-fb-{pid}-{k}"
            fallback["_occ_band"] = gap
            out.append(fallback)

    return out


@dataclass
class _Band:
    """One pre-normalised legacy row as a party band on a date span.

    The `SourceBand` payload `_load_rows` feeds the flattener: the span/bracket
    fields become the flattener's axes, `sort_id` and `legacy_id` (the unique
    per-row discriminator) build its precedence key, and the price fields ride
    along so the winning fragments can materialise `RateBand` rows once their
    covering `RatePeriod` is known.
    """

    date_from: date
    date_to: date
    min_party: int
    max_party: int
    nightly: Decimal | None
    weekly: Decimal | None
    is_poa: bool
    is_approved: bool
    is_indicative: bool
    notes: str
    legacy_id: str
    sort_id: int


def _row_to_band(row: dict[str, Any], plan: RatePlan) -> _Band | None:
    """Resolve one pre-normalised legacy row into a `_Band`, or `None` to skip.

    Pure per-row band computation (capacity clamp, occupancy-band handling,
    price/POA logic) — the plan supplies the property capacity
    (`plan.property.capacity.guests`) the upper bound falls back to. Same junk
    filters as before: inverted/zero-span dates, priceless non-POA rows, and
    brackets fully emptied by the real capacity all yield `None`.
    """
    date_from = _as_date(row.get("FromDate"))
    date_to = _as_date(row.get("ToDate"))
    if date_from is None or date_to is None or date_to <= date_from:
        # Junk filter: FromDate == ToDate (zero-span) or an inverted legacy
        # span. Legacy `VillaSeasonRate.ToDate` is *inclusive* — a night on
        # ToDate is priced and the dates carry through unshifted; the only
        # trimming is `resolve_rate_band_overlaps` breaking shared-boundary
        # overlaps between contiguous bands.
        return None
    cap = max(plan.property.capacity.guests or 1, 1)
    party = int(row.get("PartySize") or 0)
    if party <= 0:
        # Fall back to property capacity for the upper bound.
        min_party, max_party = 1, cap
    else:
        min_party, max_party = party, party
    occ_band = row.get("_occ_band")
    if occ_band is not None:
        # Occupancy band / gap-fallback row: its explicit (from, to) range is
        # the party bracket; an open top (`None`) clamps to capacity, and a
        # bracket the real capacity empties is junk.
        low, high = occ_band
        effective_high = cap if high is None else high
        if low > effective_high:
            return None
        min_party, max_party = low, effective_high
    nightly, weekly, is_poa = _row_prices(row)
    if not (nightly or weekly or is_poa):
        return None
    if is_poa:
        # POA wins over any numeric price: raterule_poa_excludes_price forbids
        # both, and a hidden "on application" price must never resurface.
        nightly = None
        weekly = None
    legacy_id = row.get("_legacy_id") or row.get("ID")
    return _Band(
        date_from=date_from,
        date_to=date_to,
        min_party=min_party,
        max_party=max_party,
        nightly=nightly,
        weekly=weekly,
        is_poa=is_poa,
        is_approved=bool(row.get("IsApprove")),
        # GAP-114: the season's rates were copied forward, not owner-confirmed
        # (NULL bit = not carried). Occupancy/fallback rows are parent copies.
        is_indicative=bool(row.get("CarriedRates")),
        notes=(row.get("Description") or "").strip(),
        legacy_id=str(legacy_id),
        sort_id=int(row["ID"]),
    )


_UNAPPROVED_NOTE = "Unapproved in legacy (IsApprove=0)"


class RateBandLoader(BaseLoader):
    """VillaSeasonRate -> RatePeriod + RateBand (period-native, GAP-056).

    Notes:
    - Skip `IsExTra=1` rows (extras, not base rates) — `ExtraLoader`
      (`loaders/extras.py`, GAP-107) ports those into `pricing.Extra`.
    - `VillaOccupencyPrice` bands are recovered here (BUG-013): the query LEFT
      JOINs the child table and `_prepare_occupancy_rows` expands a banded
      parent into one rule per band plus base-weekly gap fallbacks, keyed on a
      namespaced `legacy_id` (`occ-*`). See `_prepare_occupancy_rows`.
    - `resolve_rate_band_overlaps` pre-normalises the expanded row set (junk
      filter, boundary trim); `_load_rows` then resolves conflicts and builds
      each plan's disjoint `RatePeriod` date axis via the shared
      `flatten_rate_grid` (BUG-016, precedence `(not approved, id, disc)`) and
      hangs the surviving fragments off their covering periods. Each run is a
      full replace (purge legacy-loaded rules + periods, rebuild).
    - max_party falls back to the property's capacity when PartySize is null.
    """

    name = "rate_rule"
    target_model = RateBand
    legacy_pk_column = "ID"
    # LEFT JOIN pulls occupancy bands alongside their parent rate (BUG-013).
    # Both tables have an `Id`/`ID` PK, so every parent column is `r.`-qualified
    # to avoid an ambiguous-column error; `VillaOccupencyPrice` has no
    # `DeletedAt`, so the child is joined on `VillaSeasonRateId` alone. A banded
    # parent with no children yields one OccId-null row (the base-weekly path).
    # `IsOccupationPrice` gates band expansion so orphan child rows on a
    # non-occupancy rate can't override its flat price (matches legacy).
    # GAP-110: rows resolve to their regime plan through the SEASON's currency
    # (`SeasonCurrencyId` / `VillaCurrencyId` — the shared subselects
    # `RatePlanLoader` grouped by), never the row's own `CurrencyId`, so a
    # NULL-currency row lands where its season's plan went. The VillaSeason /
    # VillaMaster joins mirror the plan loader's universe: a live row on a
    # soft-deleted season or villa has no regime to land on.
    # GAP-114: `s.CarriedRates` exists only in the ResProd schema (drifted from
    # the committed ResSystem source — CUTOVER.md) and lands as
    # `RateBand.is_indicative`.
    legacy_query = (
        "SELECT r.ID, s.VillaId, r.SeasonId, r.CurrencyId, r.FromDate, r.ToDate, "
        "r.PartySize, r.IsPOA, r.WeeklyPrice, r.NightlyPrice, r.Price, "
        "r.PriceType, r.IsExTra, r.IsApprove, r.IsAvailable, r.Description, "
        "r.IsOccupationPrice, s.CarriedRates, "
        "o.Id AS OccId, o.OccupencyFrom, o.OccupencyTo, o.OccupencyPrice, "
        f"{SEASON_CURRENCY_SUBSELECT} AS SeasonCurrencyId, "
        f"{VILLA_CURRENCY_SUBSELECT} AS VillaCurrencyId "
        "FROM VillaSeasonRate r "
        "JOIN VillaSeason s ON s.ID = r.SeasonId AND s.DeletedAt IS NULL "
        "JOIN VillaMaster m ON m.Id = s.VillaId AND m.DeletedAt IS NULL "
        "LEFT JOIN VillaOccupencyPrice o ON o.VillaSeasonRateId = r.ID "
        "WHERE r.DeletedAt IS NULL AND r.IsExTra <> 1"
    )

    @staticmethod
    def _resolve_plan_key(
        row: dict[str, Any],
        plan_by_key: dict[str, RatePlan],
        prop_cache: dict[str, Property | None],
    ) -> str | None:
        """The regime plan a season's rows belong to: `villa:<VillaId>:<CODE>`
        via the plan loader's own currency chain, or None when the villa is
        unloaded or no such plan was minted (`plan_by_key` holds every regime
        plan up front; `prop_cache` memoises the Property per villa)."""
        villa_id = str(row.get("VillaId") or "")
        if villa_id not in prop_cache:
            prop_cache[villa_id] = Property.objects.filter(legacy_id=villa_id).first()
        prop = prop_cache[villa_id]
        if prop is None:
            return None
        currency = resolve_season_currency(
            {
                "CurrencyId": row.get("SeasonCurrencyId"),
                "VillaCurrencyId": row.get("VillaCurrencyId"),
            },
            prop,
        )
        if currency is None:
            return None
        key = plan_legacy_id(prop.legacy_id, currency.code)
        return key if key in plan_by_key else None

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        """Full replace: purge every legacy-loaded rule + period, then rebuild
        the disjoint `RatePeriod` date axis natively and hang the bands off it.

        Inserting into an empty legacy footprint means re-runs can't collide
        with last run's spans under the `rateperiod_no_overlap` /
        `rateband_bands_no_overlap` EXCLUDE constraints (in-place upserts could:
        a row expanding into — or swapping spans with — a sibling's old range
        would trip mid-run). `flatten_rate_grid` resolves each plan's
        pre-normalised bands into a (date x party)-disjoint grid (BUG-016) —
        both EXCLUDEs hold by construction. A band surviving in >1 flat cell
        (bisected by a sibling's boundary, or party-split by a winner) is
        fragmented: its first fragment keeps the legacy_id, later ones are
        namespaced `#seg{n}` in `(period date_from, min_party)` order.
        UI-created periods (legacy_id NULL) and the bands hanging off them
        survive untouched — but since GAP-110 the no-overlap EXCLUDE is
        regime-wide, so a UI period on *any* plan of the same (villa,
        currency) that overlaps a re-loaded legacy period rolls the whole
        load back (loud, total; delta loads are a cutover-window operation).
        A UI band added to a *legacy* period is
        cascade-deleted with that period (loaders run at cutover, before staff
        editing, so that window is closed in practice). A full rebuild — rather
        than sparing such bands — is what keeps re-runs clear of the
        `rateperiod_no_overlap` EXCLUDE (a spared legacy period would collide
        with the freshly re-segmented one for the same span).
        """
        rows = _prepare_occupancy_rows(rows)
        # Resolve each row's regime plan (GAP-110) BEFORE pre-normalisation so
        # the resolver groups by plan: seasons of one villa + currency trim and
        # resolve together. Rows with no plan (unloaded villa, no regime for
        # the season's currency) are skipped here — they must not trim or
        # shadow each other in a phantom group. `select_related` folds the
        # `plan.property.capacity` read `_row_to_band` does into one fetch.
        plan_by_key: dict[str, RatePlan] = {
            str(p.legacy_id): p
            for p in RatePlan.objects.filter(
                legacy_id__startswith=PLAN_LEGACY_PREFIX
            ).select_related("property__capacity")
        }
        prop_cache: dict[str, Property | None] = {}
        season_plan_key: dict[str, str | None] = {}
        resolvable: list[dict[str, Any]] = []
        for row in rows:
            season_id = str(row.get("SeasonId") or "")
            if season_id not in season_plan_key:
                season_plan_key[season_id] = self._resolve_plan_key(row, plan_by_key, prop_cache)
            key = season_plan_key[season_id]
            if key is None:
                report.skipped += 1
                continue
            row["_plan_key"] = key
            resolvable.append(row)
        resolution = resolve_rate_band_overlaps(resolvable)
        created = 0
        periods_created = 0
        rule_fragments = 0
        shadowed_dropped = 0
        party_clipped = 0
        with transaction.atomic():
            purged, _ = RateBand.objects.filter(legacy_id__isnull=False).delete()
            RatePeriod.objects.filter(legacy_id__isnull=False).delete()

            # Group the resolved rows into bands per plan (skip rows
            # `_row_to_band` rejects as junk).
            bands_by_plan: dict[int, list[_Band]] = defaultdict(list)
            plan_by_pk: dict[int, RatePlan] = {}
            for row in resolution.rows:
                plan = plan_by_key[row["_plan_key"]]
                band = _row_to_band(row, plan)
                if band is None:
                    report.skipped += 1
                    continue
                bands_by_plan[plan.pk].append(band)
                plan_by_pk[plan.pk] = plan

            for plan_pk, bands in bands_by_plan.items():
                plan = plan_by_pk[plan_pk]
                # Roll the flat-vs-occupancy shape up onto the plan: >1 distinct
                # party bracket means the villa prices by occupancy (matches the
                # engine's runtime test). Idempotent — re-runs converge.
                by_occupancy = len({(b.min_party, b.max_party) for b in bands}) > 1
                if plan.prices_by_occupancy != by_occupancy:
                    plan.prices_by_occupancy = by_occupancy
                    plan.save(update_fields=["prices_by_occupancy"])
                # Conflict resolution (BUG-016): the shared flattener resolves
                # the plan's bands into a (date x party)-disjoint grid,
                # approved-first / lowest-legacy-ID precedence, split not clip.
                sources = [
                    SourceBand(
                        date_from=b.date_from,
                        date_to=b.date_to,
                        min_party=b.min_party,
                        max_party=b.max_party,
                        precedence=(not b.is_approved, b.sort_id, b.legacy_id),
                        payload=b,
                    )
                    for b in bands
                ]
                flat = flatten_rate_grid(sources)
                shadowed_dropped += len(flat.dropped_sources)
                party_clipped += len(flat.party_clipped)
                for i, flat_period in enumerate(flat.periods):
                    # GAP-059: legacy has no period-name column (the season
                    # name lands on RatePlan), so synthesize the placeholder
                    # from the segment span — pure on the dates, keeping
                    # re-runs byte-identical.
                    period = RatePeriod.objects.create(
                        plan=plan,
                        name=derive_period_name(flat_period.date_from, flat_period.date_to),
                        date_from=flat_period.date_from,
                        date_to=flat_period.date_to,
                        legacy_id=f"{plan.legacy_id}:p{i}",
                    )
                    periods_created += 1
                    for flat_band in flat_period.bands:
                        band = flat_band.source.payload
                        if flat_band.fragment_index == 0:
                            legacy_id = band.legacy_id
                            created += 1
                        else:
                            legacy_id = f"{band.legacy_id}#seg{flat_band.fragment_index}"
                            rule_fragments += 1
                        RateBand.objects.create(
                            period=period,
                            min_party=flat_band.min_party,
                            max_party=flat_band.max_party,
                            nightly=band.nightly,
                            weekly=band.weekly,
                            is_poa=band.is_poa,
                            # BUG-028: legacy quotes ignore IsApprove, so
                            # every imported band is approved; the legacy
                            # flag still orders precedence above and stays
                            # visible in notes.
                            is_approved=True,
                            # GAP-114: payload-only — never part of precedence.
                            is_indicative=band.is_indicative,
                            notes=(
                                band.notes
                                if band.is_approved
                                else "\n".join(filter(None, [band.notes, _UNAPPROVED_NOTE]))
                            ),
                            legacy_id=legacy_id,
                        )
        report.created += created
        logger.info(
            "data_migration.rate_rule_overlaps_resolved",
            trimmed=resolution.trimmed,
            dropped=resolution.dropped,
            shadowed_dropped=shadowed_dropped,
            party_clipped=party_clipped,
            purged=purged,
            periods_created=periods_created,
            rule_fragments=rule_fragments,
        )
