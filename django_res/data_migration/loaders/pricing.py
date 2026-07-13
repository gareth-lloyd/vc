"""Pricing: VillaSeason -> RatePlan; VillaSeasonRate -> RatePeriod + RateBand.

Legacy structure:
  VillaSeason (id, name, villa_id, notes, inclusion)
    └── VillaSeasonDates (id, season_id, from_date, to_date)
    └── VillaSeasonRate (id, season_id, villa_id, currency_id, from_date,
                        to_date, party_size, price_type, weekly_price,
                        nightly_price, is_poa, ...)

New structure (GAP-056):
  RatePlan (property, currency, effective_from, effective_to)
    └── RatePeriod (plan, date_from, date_to)  — disjoint date axis
          └── RateBand (period, min_party, max_party, nightly, weekly, is_poa)

Strategy:
- One RatePlan per VillaSeason. Currency comes from the season's own
  non-NULL VillaSeasonRate rows (most recent first); a season with only
  NULL/0 CurrencyId rows falls back to the villa's other non-NULL rate rows,
  then settings → EUR — never `Currency.objects.first()` (GAP-014 step 0),
  and never `resolve_property_currency`, whose plans-first step reads the
  very table this loader populates (load-order dependent, and a wrong stamp
  would re-resolve from itself forever on idempotent re-runs).
- effective_from/to from min/max of VillaSeasonDates rows.
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


def _row_prices(row: dict[str, Any]) -> tuple[Decimal | None, Decimal | None, Decimal | None, bool]:
    """The price columns of a VillaSeasonRate row, shared by the overlap
    resolver's pre-filter and `transform` so the skip predicate can't drift."""
    return (
        _to_decimal(row.get("NightlyPrice")),
        _to_decimal(row.get("WeeklyPrice")),
        _to_decimal(row.get("Price")),
        bool(row.get("IsPOA")),
    )


def _has_price(row: dict[str, Any]) -> bool:
    nightly, weekly, price, is_poa = _row_prices(row)
    return bool(nightly or weekly or price or is_poa)


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

    1. Pre-filter rows `transform()` would skip (junk dates, no price and not
       POA) so they can neither trim nor be trimmed. Within a season, exact
       duplicates sharing a `_legacy_id` discriminator are dropped (keep the
       first) — unreachable off real SQL PKs, but dirty input must not reach
       the flattener's duplicate-precedence ValueError.
    2. Boundary trim: legacy stored checkout-style contiguous bands (the next
       row starts on the day the previous one ends) but the new model is
       inclusive on both ends — trim one day off the earlier row's end.
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
        season = row.get("SeasonId")
        if disc in seen_discs[season]:
            dropped += 1
            continue
        seen_discs[season].add(disc)
        groups[season].append(
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
            if item.date_to <= item.date_from:
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


class RatePlanLoader(BaseLoader):
    """VillaSeason -> RatePlan.

    Picks currency + dates from related VillaSeasonRate / VillaSeasonDates.
    The plan owns no rate rows here — `RateBandLoader` builds its `RatePeriod`
    date axis and party bands. `_process_row` additionally materialises the
    season's free-text Inclusion as a `PropertyService` (GAP-037).
    """

    name = "rate_plan"
    target_model = RatePlan
    legacy_pk_column = "ID"
    # CurrencyId: the season's own most recent non-NULL/non-zero rate row.
    # VillaCurrencyId: same, but across ALL the villa's seasons — the GAP-014
    # rule-1 inference for the 2023-era seasons whose rows are all NULL but
    # whose villa later got real currencies.
    legacy_query = (
        "SELECT s.ID, s.Name, s.VillaId, s.Notes, s.Inclusion, "
        "(SELECT TOP 1 r.CurrencyId FROM VillaSeasonRate r "
        " WHERE r.SeasonId = s.ID AND r.CurrencyId IS NOT NULL AND r.CurrencyId <> 0 "
        " AND r.DeletedAt IS NULL ORDER BY r.ID DESC) AS CurrencyId, "
        "(SELECT TOP 1 r2.CurrencyId FROM VillaSeasonRate r2 "
        " WHERE r2.VillaId = s.VillaId AND r2.CurrencyId IS NOT NULL AND r2.CurrencyId <> 0 "
        " AND r2.DeletedAt IS NULL ORDER BY r2.ID DESC) AS VillaCurrencyId, "
        "(SELECT MIN(d.FromDate) FROM VillaSeasonDates d WHERE d.SeasonId = s.ID) AS DateFrom, "
        "(SELECT MAX(d.ToDate) FROM VillaSeasonDates d WHERE d.SeasonId = s.ID) AS DateTo "
        "FROM VillaSeason s WHERE s.DeletedAt IS NULL"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        prop = Property.objects.filter(legacy_id=str(row.get("VillaId") or "")).first()
        if prop is None:
            return None
        currency = Currency.objects.filter(legacy_id=str(row.get("CurrencyId") or "")).first()
        if currency is None:
            # Season has only NULL/0 currency rows — infer from the villa's
            # other rate rows, then the canonical settings → EUR chain.
            currency = Currency.objects.filter(
                legacy_id=str(row.get("VillaCurrencyId") or "")
            ).first()
        if currency is None:
            # Settings → EUR only: `resolve_property_currency`'s plans-first
            # step would read the RatePlan rows this loader writes, so a
            # mis-stamped currency could never self-correct on a re-run.
            currency = settings_currency(prop) or default_currency()
            if currency is None:
                return None
        effective_from = _as_date(row.get("DateFrom")) or date(2020, 1, 1)
        effective_to = _as_date(row.get("DateTo"))
        return {
            "property": prop,
            "name": (row.get("Name") or f"Season {row['ID']}")[:128],
            "currency": currency,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "is_active": True,
            "notes": (row.get("Notes") or "").strip(),
            # GAP-037: `Inclusion` no longer lands on RatePlan — it materialises a
            # PropertyService in `_process_row` (keyed `<season>:svc`).
            # SMELL-021: stamped explicitly, not left to the model default.
            # Legacy has no per-villa NET/GROSS signal — `RatesModel.Calculate()`
            # always treats the entered rate as the guest-facing gross
            # (`GrossPrice = getWeeklyPrice`, net derived by subtracting
            # tax + commission) — so every imported plan is GROSS by rule.
            # `reconcile_legacy` pins the invariant (zero non-GROSS legacy plans).
            "price_basis": PriceBasis.GROSS,
        }

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        super()._process_row(row, report)
        legacy_id = row.get(self.legacy_pk_column)
        if legacy_id is None:
            return
        plan = RatePlan.objects.filter(legacy_id=str(legacy_id)).first()
        if plan is None:
            return
        # GAP-037: a season's free-text Inclusion becomes one date-banded
        # PropertyService on the villa, sharing the plan's effective dates.
        inclusion = (row.get("Inclusion") or "").strip()
        if inclusion:
            PropertyService.objects.update_or_create(
                legacy_id=f"{legacy_id}:svc",
                defaults={
                    "property": plan.property,
                    "name": "Included services",
                    "copy": inclusion,
                    "applies_from": plan.effective_from,
                    "applies_to": plan.effective_to,
                    "is_active": plan.is_active,
                },
            )


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
                if frm <= 0 or to <= 0 or frm > to:
                    continue
                price = _to_decimal(row.get("OccupencyPrice"))
                if not price:
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
            band["Price"] = None
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
    nightly, weekly, price, is_poa = _row_prices(row)
    if not (nightly or weekly or price or is_poa):
        return None
    # If only Price is set, treat it as nightly.
    if nightly is None and weekly is None and price is not None:
        nightly = price
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
        notes=(row.get("Description") or "").strip(),
        legacy_id=str(legacy_id),
        sort_id=int(row["ID"]),
    )


class RateBandLoader(BaseLoader):
    """VillaSeasonRate -> RatePeriod + RateBand (period-native, GAP-056).

    Notes:
    - Skip `IsExTra=1` rows (extras, not base rates).
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
    legacy_query = (
        "SELECT r.ID, r.VillaId, r.SeasonId, r.CurrencyId, r.FromDate, r.ToDate, "
        "r.PartySize, r.IsPOA, r.WeeklyPrice, r.NightlyPrice, r.Price, "
        "r.PriceType, r.IsExTra, r.IsApprove, r.IsAvailable, r.Description, "
        "r.IsOccupationPrice, "
        "o.Id AS OccId, o.OccupencyFrom, o.OccupencyTo, o.OccupencyPrice "
        "FROM VillaSeasonRate r "
        "LEFT JOIN VillaOccupencyPrice o ON o.VillaSeasonRateId = r.ID "
        "WHERE r.DeletedAt IS NULL AND r.IsExTra <> 1"
    )

    def _apply_since(self, query: str) -> str:
        # Deliberate no-op: overlap resolution is a function of a season's
        # whole row set, so a `--since` delta would mis-trim against rows it
        # can't see. The table is small; every pass is a full reload.
        if self.since:
            logger.warning(
                "data_migration.rate_rule_since_ignored",
                since=str(self.since),
                reason="overlap resolution needs the full row set; full reload",
            )
        return query

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
        survive untouched; a UI band added to a *legacy* period is
        cascade-deleted with that period (loaders run at cutover, before staff
        editing, so that window is closed in practice). A full rebuild — rather
        than sparing such bands — is what keeps re-runs clear of the
        `rateperiod_no_overlap` EXCLUDE (a spared legacy period would collide
        with the freshly re-segmented one for the same span).
        """
        rows = _prepare_occupancy_rows(rows)
        resolution = resolve_rate_band_overlaps(rows)
        created = 0
        periods_created = 0
        rule_fragments = 0
        shadowed_dropped = 0
        party_clipped = 0
        with transaction.atomic():
            purged, _ = RateBand.objects.filter(legacy_id__isnull=False).delete()
            RatePeriod.objects.filter(legacy_id__isnull=False).delete()

            # Group the resolved rows into bands per plan (skip rows whose season
            # has no loaded RatePlan, or that `_row_to_band` rejects as junk).
            bands_by_plan: dict[int, list[_Band]] = defaultdict(list)
            plan_by_pk: dict[int, RatePlan] = {}
            plan_cache: dict[str, RatePlan | None] = {}
            for row in resolution.rows:
                season_id = str(row.get("SeasonId") or "")
                if season_id not in plan_cache:
                    # `select_related` folds the `plan.property.capacity` read
                    # `_row_to_band` does (the capacity clamp) into this fetch —
                    # otherwise the first band per plan fires two extra queries.
                    plan_cache[season_id] = (
                        RatePlan.objects.filter(legacy_id=season_id)
                        .select_related("property__capacity")
                        .first()
                    )
                plan = plan_cache[season_id]
                if plan is None:
                    report.skipped += 1
                    continue
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
                            is_approved=band.is_approved,
                            notes=band.notes,
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
