"""GAP-110 / CUTOVER.md §5 item 5: legacy-quote sample on cross-season overlap villas.

Read-only. Finds live villas whose legacy `VillaSeasonRate` rows overlap across
seasons for the same party (the shapes `RateBandLoader` resolves across seasons
by `(not approved, id, disc)`), then re-prices the loaded legacy quotation lines
on those villas with `PricingEngine.quote` and compares against legacy `Price`.

Legacy `VillaQuotationDetails.Price` is the RENTAL figure only: `ResService`
sums `WeeklyPrice / 7` per night (an occupancy child's `round(OccupencyPrice / 7,
2)`), then `Math.Round`s the stay to a whole unit (banker's rounding) — no
extras, discounts, commission or tax. So it is compared with `quote.rate_subtotal`:
"exact" = the subtotal rounded HALF_EVEN to a whole unit equals `Price`,
"within 1.00" = |subtotal - Price| <= 1.00.

Run from `django_res/`:

    DATABASE_URL=postgres://villa:villa@localhost:55432/villacollective_gap108 \
    LEGACY_DATABASE_URL='mssql://sa:ResLocal%212026@localhost:11433/ResProd' \
    uv run python manage.py shell -c \
    "exec(open('../.claude-tmp/gap110-quote-sample.py').read())"
"""

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from django.db import transaction

from core.exceptions import DomainError
from data_migration.legacy_db import legacy_cursor, rows_as_dicts
from data_migration.loaders._util import legacy_deleted_sql, live_villa_sql
from data_migration.loaders.pricing import (
    SEASON_CURRENCY_SUBSELECT,
    VILLA_CURRENCY_SUBSELECT,
    _as_date,
    _prepare_occupancy_rows,
    resolve_rate_band_overlaps,
)
from pricing.services.engine import PricingEngine
from pricing.services.intervals import Interval, intervals_overlap
from reservations.models.quotation import QuotationLine

MAX_LINES = 3000  # cap on engine calls; lines are taken in (villa, line id) order
MAX_MISMATCH_ROWS = 30

# The RateBandLoader row universe, with the stricter GAP-108 deleted/live filters.
RATES_SQL = (
    "SELECT r.ID, s.VillaId, r.SeasonId, r.FromDate, r.ToDate, r.PartySize, r.IsPOA, "
    "r.WeeklyPrice, r.NightlyPrice, r.IsApprove, r.IsOccupationPrice, "
    "o.Id AS OccId, o.OccupencyFrom, o.OccupencyTo, o.OccupencyPrice, "
    f"{SEASON_CURRENCY_SUBSELECT} AS SeasonCurrencyId, "
    f"{VILLA_CURRENCY_SUBSELECT} AS VillaCurrencyId "
    "FROM VillaSeasonRate r "
    f"JOIN VillaSeason s ON s.ID = r.SeasonId AND NOT {legacy_deleted_sql('s.')} "
    f"JOIN VillaMaster m ON m.Id = s.VillaId AND {live_villa_sql('m.')} "
    "LEFT JOIN VillaOccupencyPrice o ON o.VillaSeasonRateId = r.ID "
    f"WHERE NOT {legacy_deleted_sql('r.')} AND r.IsExTra <> 1 "
    "ORDER BY r.ID, o.Id"
)


def party_intervals(row: dict[str, Any]) -> list[Interval]:
    """Same party coverage `resolve_rate_band_overlaps` assigns a row."""
    band = row.get("_occ_band")
    if band is not None:
        return [band]
    party = int(row.get("PartySize") or 0)
    return [(party, party)] if party > 0 else [(1, None)]


def in_list(ids: list[int]) -> str:
    return ",".join(str(int(i)) for i in ids)


# --- 1. Legacy: cross-season same-party overlaps -----------------------------
with legacy_cursor() as cur:
    cur.execute(RATES_SQL)
    raw = list(rows_as_dicts(cur))
for r in raw:
    r["_parent_id"] = r["ID"]  # band rows swap ID for OccId; keep the parent
    r["_plan_key"] = f"{r['VillaId']}:{r['SeasonCurrencyId'] or r['VillaCurrencyId']}"

resolved = resolve_rate_band_overlaps(_prepare_occupancy_rows(raw)).rows
by_plan: dict[str, list[dict[str, Any]]] = defaultdict(list)
for r in resolved:
    by_plan[r["_plan_key"]].append(r)

pairs: set[tuple[int, int]] = set()
exact_party_pairs: set[tuple[int, int]] = set()
exact_party_villas: set[int] = set()
# villa -> [(from, to, party intervals of both rows)] overlap zones (inclusive dates)
zones: dict[int, list[tuple[date, date, list[Interval], list[Interval]]]] = defaultdict(list)
for rows in by_plan.values():
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            if a["SeasonId"] == b["SeasonId"]:
                continue
            lo = max(_as_date(a["FromDate"]), _as_date(b["FromDate"]))
            hi = min(_as_date(a["ToDate"]), _as_date(b["ToDate"]))
            if lo > hi:
                continue
            pa, pb = party_intervals(a), party_intervals(b)
            if not any(intervals_overlap(x, y) for x in pa for y in pb):
                continue
            key = tuple(sorted((a["_parent_id"], b["_parent_id"])))
            pairs.add(key)  # type: ignore[arg-type]
            if pa == pb and pa[0][1] is not None and "_occ_band" not in a | b:
                exact_party_pairs.add(key)  # type: ignore[arg-type]
                exact_party_villas.add(int(a["VillaId"]))
            zones[int(a["VillaId"])].append((lo, hi, pa, pb))

overlap_villas = sorted(zones)
print(f"legacy priced rate rows (expanded, resolved): {len(resolved)}")
print(
    f"cross-season same-party overlaps: {len(pairs)} rate-row pairs on {len(overlap_villas)} villas"
)
print(
    f"  of which both rows share one explicit PartySize (no open/occupancy range): "
    f"{len(exact_party_pairs)} pairs on {len(exact_party_villas)} villas"
)
if not overlap_villas:
    raise SystemExit(0)

# Drift guard: newest rate-row touch per villa (created / updated / deleted, any
# row incl. soft-deleted ones — a delete changes the price too).
with legacy_cursor() as cur:
    cur.execute(
        "SELECT s.VillaId, MAX(x.ts) AS LastTouch FROM VillaSeasonRate r "
        "JOIN VillaSeason s ON s.ID = r.SeasonId "
        "CROSS APPLY (VALUES (r.CreatedAt), (r.UpdatedAt), (r.DeletedAt)) x(ts) "
        f"WHERE ISNULL(r.IsExTra, 0) <> 1 AND s.VillaId IN ({in_list(overlap_villas)}) "
        "GROUP BY s.VillaId"
    )
    last_touch = {int(row["VillaId"]): row["LastTouch"] for row in rows_as_dicts(cur)}


def in_overlap_zone(villa: int, date_from: date, date_to: date, party: int) -> bool:
    last_night = date_to - timedelta(days=1)
    for lo, hi, pa, pb in zones[villa]:
        if lo <= last_night and date_from <= hi:
            me: Interval = (party, party)
            if any(intervals_overlap(me, x) for x in pa) and any(
                intervals_overlap(me, y) for y in pb
            ):
                return True
    return False


# --- 2. Loaded quotation lines on those villas ------------------------------
lines = list(
    QuotationLine.objects.real()
    .filter(property__legacy_id__in=[str(v) for v in overlap_villas], is_manual=False)
    .select_related("property", "currency", "quotation")
    .order_by("pk")
)
lines.sort(key=lambda ln: (int(ln.property.legacy_id), int(ln.legacy_id or 0), ln.pk))

master_ids = sorted({int(ln.quotation.legacy_id) for ln in lines if ln.quotation.legacy_id})
masters: dict[int, dict[str, Any]] = {}
with legacy_cursor() as cur:
    for k in range(0, len(master_ids), 1000):
        chunk = master_ids[k : k + 1000]
        cur.execute(
            "SELECT Id, CreatedAt, Guests, Adult, Children FROM VillaQuotationMaster "
            f"WHERE Id IN ({in_list(chunk)})"
        )
        masters.update({int(row["Id"]): row for row in rows_as_dicts(cur)})

skips: Counter[str] = Counter()
sample: list[tuple[QuotationLine, dict[str, Any]]] = []
for ln in lines:
    master = masters.get(int(ln.quotation.legacy_id or 0))
    villa = int(ln.property.legacy_id)
    if ln.adults + ln.children <= 0:
        skips["party 0"] += 1
    elif master is None or master["CreatedAt"] is None:
        skips["no legacy master CreatedAt"] += 1
    elif last_touch.get(villa) is not None and master["CreatedAt"] <= last_touch[villa]:
        skips["quoted before villa's last rate-row touch"] += 1
    elif ln.total <= 0:
        skips["legacy Price 0"] += 1
    else:
        sample.append((ln, master))
if len(sample) > MAX_LINES:
    skips[f"over MAX_LINES={MAX_LINES}"] = len(sample) - MAX_LINES
    sample = sample[:MAX_LINES]

# --- 3. Re-price with the engine (rolled back: the engine must not write) ----
exact = within = shifted = guests_differ = 0
errors: Counter[str] = Counter()
mismatches: list[tuple[Any, ...]] = []
mismatch_in_zone = 0
villas_sampled: set[int] = set()
with transaction.atomic():
    for ln, master in sample:
        villa = int(ln.property.legacy_id)
        villas_sampled.add(villa)
        party = ln.adults + ln.children
        if master["Guests"] is not None and int(master["Guests"]) != party:
            guests_differ += 1
        try:
            quote = PricingEngine.quote(
                property=ln.property,
                date_from=ln.date_from,
                date_to=ln.date_to,
                party=party,
                currency=ln.currency,
                as_of=_as_date(master["CreatedAt"]),
            )
        except DomainError as exc:
            errors[type(exc).__name__] += 1
            continue
        if quote.changeover_shifted_from is not None:
            shifted += 1
            continue
        legacy = ln.total
        engine = quote.rate_subtotal
        if engine.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN) == legacy:
            exact += 1
        elif abs(engine - legacy) <= Decimal("1.00"):
            within += 1
        else:
            zone = in_overlap_zone(villa, ln.date_from, ln.date_to, party)
            mismatch_in_zone += zone
            mismatches.append(
                (
                    villa,
                    ln.quotation.number or ln.quotation.reference,
                    ln.date_from,
                    ln.date_to,
                    party,
                    ln.currency.code,
                    legacy,
                    engine,
                    engine - legacy,
                    "Y" if zone else "",
                )
            )
    transaction.set_rollback(True)

# --- 4. Report ---------------------------------------------------------------
print()
print(f"quotation lines on overlap villas (non-manual, real): {len(lines)}")
for reason, n in sorted(skips.items()):
    print(f"  skipped - {reason}: {n}")
print(f"lines sampled: {len(sample)} on {len(villas_sampled)} villas")
print(f"  match exact (subtotal rounded to whole unit == Price): {exact}")
print(f"  match within 1.00: {within}")
print(f"  mismatch: {len(mismatches)} (stay touches an overlap zone: {mismatch_in_zone})")
print(f"  changeover-shifted (not compared): {shifted}")
for name, n in sorted(errors.items()):
    print(f"  error {name}: {n}")
print(f"  (master Guests != Adult+Children on {guests_differ} sampled lines)")

if mismatches:
    print()
    print(
        f"{'villa':>5} {'quote':>7} {'from':>10} {'to':>10} {'pty':>3} {'cur':>3} "
        f"{'legacy':>10} {'engine':>10} {'delta':>10} zone"
    )
    worst = sorted(mismatches, key=lambda m: (-abs(m[8]), m[0], str(m[1]), m[2]))
    for m in sorted(worst[:MAX_MISMATCH_ROWS], key=lambda m: (m[0], str(m[1]), m[2])):
        print(
            f"{m[0]:>5} {m[1]!s:>7} {m[2]!s:>10} {m[3]!s:>10} {m[4]:>3} {m[5]:>3} "
            f"{m[6]:>10} {m[7]:>10} {m[8]:>10} {m[9]}"
        )
