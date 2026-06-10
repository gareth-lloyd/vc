"""Pricing: VillaSeason -> RatePlan + RateCard; VillaSeasonRate -> RateRule.

Legacy structure:
  VillaSeason (id, name, villa_id, notes, inclusion)
    └── VillaSeasonDates (id, season_id, from_date, to_date)
    └── VillaSeasonRate (id, season_id, villa_id, currency_id, from_date,
                        to_date, party_size, price_type, weekly_price,
                        nightly_price, is_poa, ...)

New structure:
  RatePlan (property, currency, effective_from, effective_to)
    └── RateCard (plan, name, ...)
          └── RateRule (card, date_from, date_to, min_party, max_party,
                       nightly, weekly, is_poa)

Strategy:
- One RatePlan per VillaSeason (currency picked from first VillaSeasonRate).
- effective_from/to from min/max of VillaSeasonDates rows.
- One default RateCard per RatePlan (named after the season).
- One VillaSeasonRate -> at most one RateRule: `resolve_rate_rule_overlaps`
  trims/drops overlapping legacy rows before the upsert (legacy had no
  precedence concept — see "Rate rule overlap resolution" in
  data_migration/CUTOVER.md).
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
from pricing.models.rate import RateCard, RatePlan, RateRule
from properties.models.property import Property

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
    """Outcome of `resolve_rate_rule_overlaps`: surviving rows + counters."""

    rows: list[dict[str, Any]]
    trimmed: int
    dropped: int
    party_clipped: int


_Interval = tuple[int, int | None]


@dataclass
class _WorkRow:
    """Mutable working copy of one legacy row during resolution.

    `party_intervals` is the row's authoritative party coverage: inclusive
    `(low, high)` brackets, `high=None` meaning "up to property capacity" —
    treated as unbounded so the resolver stays pure (capacity is resolved
    later, in `transform`). Conflict checks and clips operate on the whole
    set, so whichever interval `transform` later picks is conflict-free.
    """

    id: int
    row: dict[str, Any]
    orig_from: date
    date_from: date
    date_to: date
    party_intervals: list[_Interval]
    approved: bool
    party_clipped: bool = False


def _intervals_overlap(a: _Interval, b: _Interval) -> bool:
    return (a[1] is None or b[0] <= a[1]) and (b[1] is None or a[0] <= b[1])


def _party_overlap(a: _WorkRow, b: _WorkRow) -> bool:
    return any(_intervals_overlap(i, j) for i in a.party_intervals for j in b.party_intervals)


def _date_remainder(loser: _WorkRow, winner: _WorkRow) -> tuple[date, date] | None:
    """Largest valid remainder of the loser's date span minus the winner's.

    Clip-only: when the winner sits strictly inside the loser, the smaller
    side is discarded rather than splitting into two rows. Remainders must
    satisfy the model's strict `date_from < date_to`, mirroring transform's
    skip rule.
    """
    left = (loser.date_from, winner.date_from - timedelta(days=1))
    right = (winner.date_to + timedelta(days=1), loser.date_to)
    candidates = [span for span in (left, right) if span[0] < span[1]]
    if not candidates:
        return None
    return max(candidates, key=lambda span: span[1] - span[0])


def _subtract_party(intervals: list[_Interval], winner: list[_Interval]) -> list[_Interval]:
    """Remainders of `intervals` minus every winner interval, highest bracket
    first. `transform` prefers the first interval; lower ones are fallbacks
    for when property capacity empties it (`None` upper bound = capacity,
    unknown here)."""
    remaining = list(intervals)
    for wlo, whi in winner:
        survivors: list[_Interval] = []
        for lo, hi in remaining:
            if not _intervals_overlap((lo, hi), (wlo, whi)):
                survivors.append((lo, hi))
                continue
            if whi is not None and (hi is None or whi < hi):
                survivors.append((whi + 1, hi))
            if lo < wlo:
                survivors.append((lo, wlo - 1))
        remaining = survivors
    return sorted(remaining, key=lambda iv: iv[0], reverse=True)


def resolve_rate_rule_overlaps(rows: list[dict[str, Any]]) -> OverlapResolution:
    """Resolve legacy VillaSeasonRate overlaps before loading.

    Legacy had no precedence concept (its per-night lookup was an unordered
    `TOP 1`), so overlapping rows are data noise to resolve, not behaviour to
    preserve. Policy (user-confirmed, see CUTOVER.md):

    1. Pre-filter rows `transform()` would skip (junk dates, no price and not
       POA) so they can neither trim nor be trimmed.
    2. Boundary trim: legacy stored checkout-style contiguous bands (the next
       row starts on the day the previous one ends) but the new model is
       inclusive on both ends — trim one day off the earlier row's end.
       Compares *original* FromDates (never modified), so chains trim cleanly
       and the pass is order-independent.
    3. Conflict resolution: approved rows claim space before unapproved ones;
       within each tier the lowest legacy ID wins. Losers are clipped to the
       uncovered remainder or dropped when fully covered. Rows with identical
       date spans clip the party bracket instead, recording the surviving
       intervals on `_party_intervals`.

    Pure function of the input row set — deterministic, order-independent,
    DB-free. One input row maps to zero or one output rows, legacy ID
    unchanged.
    """
    trimmed = dropped = party_clipped = 0

    groups: dict[Any, list[_WorkRow]] = defaultdict(list)
    for row in rows:
        date_from = _as_date(row.get("FromDate"))
        date_to = _as_date(row.get("ToDate"))
        if date_from is None or date_to is None or date_to <= date_from:
            continue
        if not _has_price(row):
            continue
        party = int(row.get("PartySize") or 0)
        intervals: list[_Interval] = [(party, party)] if party > 0 else [(1, None)]
        groups[row.get("SeasonId")].append(
            _WorkRow(
                id=int(row["ID"]),
                row=row,
                orig_from=date_from,
                date_from=date_from,
                date_to=date_to,
                party_intervals=intervals,
                approved=bool(row.get("IsApprove")),
            )
        )

    kept_all: list[_WorkRow] = []
    for items in groups.values():
        survivors: list[_WorkRow] = []
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
                survivors.append(item)

        kept: list[_WorkRow] = []
        for item in sorted(survivors, key=lambda it: (not it.approved, it.id)):
            alive = True
            for winner in kept:
                if not _party_overlap(item, winner):
                    continue
                if item.date_from > winner.date_to or item.date_to < winner.date_from:
                    continue
                if (item.date_from, item.date_to) == (winner.date_from, winner.date_to):
                    remainders = _subtract_party(item.party_intervals, winner.party_intervals)
                    if not remainders:
                        alive = False
                        dropped += 1
                        break
                    item.party_intervals = remainders
                    item.party_clipped = True
                    party_clipped += 1
                    continue
                remainder = _date_remainder(item, winner)
                if remainder is None:
                    alive = False
                    dropped += 1
                    break
                item.date_from, item.date_to = remainder
                trimmed += 1
            if alive:
                kept.append(item)
        kept_all.extend(kept)

    out_rows: list[dict[str, Any]] = []
    for item in sorted(kept_all, key=lambda it: it.id):
        out = dict(item.row)
        out["FromDate"] = item.date_from
        out["ToDate"] = item.date_to
        if item.party_clipped:
            out["_party_intervals"] = item.party_intervals
        out_rows.append(out)
    return OverlapResolution(
        rows=out_rows,
        trimmed=trimmed,
        dropped=dropped,
        party_clipped=party_clipped,
    )


def _resolve_property_currency(prop: Property) -> Currency | None:
    """Resolve currency via the canonical PropertySettings.effective() chain,
    with a table-wide first-row fallback when neither property nor group
    has one configured.
    """
    try:
        currency = prop.settings.effective("currency")
    except Exception:
        currency = None
    return currency or Currency.objects.first()


class RatePlanLoader(BaseLoader):
    """VillaSeason -> RatePlan + default RateCard.

    Picks currency + dates from related VillaSeasonRate / VillaSeasonDates.
    Creates exactly one RateCard per plan (the framework writes it via
    `_process_row` after the plan upsert lands).
    """

    name = "rate_plan"
    target_model = RatePlan
    legacy_pk_column = "ID"
    legacy_query = (
        "SELECT s.ID, s.Name, s.VillaId, s.Notes, s.Inclusion, "
        "(SELECT TOP 1 r.CurrencyId FROM VillaSeasonRate r "
        " WHERE r.SeasonId = s.ID ORDER BY r.ID) AS CurrencyId, "
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
            # Prefer the property/group's own configured currency; only fall
            # back to the table-wide first row when neither is set.
            currency = _resolve_property_currency(prop)
            if currency is None:
                return None
        effective_from = row.get("DateFrom") or date(2020, 1, 1)
        if isinstance(effective_from, str):
            effective_from = date.fromisoformat(effective_from[:10])
        elif hasattr(effective_from, "date"):
            effective_from = effective_from.date()
        effective_to = row.get("DateTo")
        if effective_to and hasattr(effective_to, "date"):
            effective_to = effective_to.date()
        return {
            "property": prop,
            "name": (row.get("Name") or f"Season {row['ID']}")[:128],
            "currency": currency,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "is_active": True,
            "notes": (row.get("Notes") or "").strip(),
            "inclusion": (row.get("Inclusion") or "").strip(),
        }

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        super()._process_row(row, report)
        legacy_id = row.get(self.legacy_pk_column)
        if legacy_id is None:
            return
        plan = RatePlan.objects.filter(legacy_id=str(legacy_id)).first()
        if plan is None:
            return
        RateCard.objects.update_or_create(
            legacy_id=str(legacy_id),
            defaults={
                "plan": plan,
                "name": plan.name[:128],
                "min_nights": 1,
                "sort_order": 0,
                "is_active": True,
            },
        )


class RateRuleLoader(BaseLoader):
    """VillaSeasonRate -> RateRule on the season's default RateCard.

    Notes:
    - Skip `IsExTra=1` rows (extras, not base rates).
    - `resolve_rate_rule_overlaps` runs over the full row set first, so the
      inserted rules are overlap-free per card; each run is a full replace
      (purge legacy-loaded rules, reinsert) — see `_load_rows`.
    - max_party falls back to the property's capacity when PartySize is null.
    """

    name = "rate_rule"
    target_model = RateRule
    legacy_pk_column = "ID"
    legacy_query = (
        "SELECT ID, VillaId, SeasonId, CurrencyId, FromDate, ToDate, "
        "PartySize, IsPOA, WeeklyPrice, NightlyPrice, Price, "
        "PriceType, IsExTra, IsApprove, IsAvailable, Description "
        "FROM VillaSeasonRate WHERE DeletedAt IS NULL AND IsExTra <> 1"
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
        """Full replace: purge every legacy-loaded rule, then insert the
        resolver's output. Inserting into an empty legacy footprint means
        re-runs can't collide with last run's spans under the
        `raterule_no_overlap` EXCLUDE constraint (in-place upserts could:
        a row expanding into — or swapping spans with — a sibling's old
        range would trip it mid-run). UI-created rules (legacy_id NULL)
        are never touched.
        """
        resolution = resolve_rate_rule_overlaps(rows)
        with transaction.atomic():
            purged, _ = RateRule.objects.filter(legacy_id__isnull=False).delete()
            super()._load_rows(resolution.rows, report)
        logger.info(
            "data_migration.rate_rule_overlaps_resolved",
            trimmed=resolution.trimmed,
            dropped=resolution.dropped,
            party_clipped=resolution.party_clipped,
            purged=purged,
        )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        card = RateCard.objects.filter(legacy_id=str(row.get("SeasonId") or "")).first()
        if card is None:
            return None
        date_from = _as_date(row.get("FromDate"))
        date_to = _as_date(row.get("ToDate"))
        if date_from is None or date_to is None:
            return None
        if date_to <= date_from:
            # Zero-length / inverted ranges violate raterule_date_from_lt_date_to.
            return None
        party = int(row.get("PartySize") or 0)
        if party <= 0:
            # Fall back to property capacity for the upper bound.
            cap = card.plan.property.capacity.guests or 1
            min_party, max_party = 1, max(cap, 1)
        else:
            min_party, max_party = party, party
        intervals = row.get("_party_intervals")
        if intervals:
            # The resolver clipped this row's party bracket; pick the first
            # interval that survives the property's real capacity.
            cap = max(card.plan.property.capacity.guests or 1, 1)
            for low, high in intervals:
                effective_high = cap if high is None else high
                if low <= effective_high:
                    min_party, max_party = low, effective_high
                    break
            else:
                return None
        nightly, weekly, price, is_poa = _row_prices(row)
        if not (nightly or weekly or price or is_poa):
            return None
        # If only Price is set, treat it as nightly.
        if nightly is None and weekly is None and price is not None:
            nightly = price
        if is_poa:
            # POA wins over any numeric price: raterule_poa_excludes_price
            # forbids both, and a hidden "on application" price must never
            # resurface as a concrete rate.
            nightly = None
            weekly = None
        return {
            "card": card,
            "date_from": date_from,
            "date_to": date_to,
            "min_party": min_party,
            "max_party": max_party,
            "nightly": nightly,
            "weekly": weekly,
            "is_poa": is_poa,
            "is_approved": bool(row.get("IsApprove")),
            "notes": (row.get("Description") or "").strip(),
        }
