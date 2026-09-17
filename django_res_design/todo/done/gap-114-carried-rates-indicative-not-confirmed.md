# GAP-114 — `VillaSeason.CarriedRates`: 6 864 quotable rate rows the owner has not confirmed

> **✅ RESOLVED (2026-09-17)** — shipped on `feat/gap-114`; fast-forwarded into
> local `main` (unpushed) at close-out. The flag lives on the **band**, not the
> retired `RateCard`: `RateBand.is_indicative` (bool, audit-tracked so "who
> confirmed, when" comes from the trail — U1 `79ba575d`, decision row in
> `design/decisions.md`). `RateBandLoader` reads `VillaSeason.CarriedRates`
> (a ResProd-only nullable bit) per source row, so occupancy children, `occ-fb-*`
> fallbacks and `#seg` fragments inherit it and flattener precedence is
> untouched (U2 `36efdbc8`). `PricingEngine.quote` sets `Quote.is_indicative` /
> `breakdown["is_indicative"]` when any priced night uses such a band;
> projection inherits it from the anchor (U3 `7a74e425`). New reconcile check
> `RateBand indicative (CarriedRates)`, pinned on a fresh ResProd dry run:
> 1 616 carried sources → 1 421 indicative bands, gap 195 itemised to zero
> residual (+218 shadowed − 2 `occ-fb-*` − 21 `#seg`); `RateBand` gap still 462
> (U4 `b74a82cb`). Staff carry-forward writes indicative bands;
> `POST /rate-plans/{id}:confirm-rates` (optional date window, non-historical
> periods only, audited per band) and a writable band flag clear it
> (U5 `4634b346`). The quote builder fan-out/weekly rows and
> `QuotationLineSerializer.is_indicative` (a pricing-time snapshot fact) expose
> it; conversion and booking modify carry it (U6 `32f5c9d9`). **Business
> decision: staff-only warning, never a block** — "Indicative rates" badges on
> the result card (picked week + flagged bands), shortlist, saved lines and the
> workbench probe, warnings in the send-preview and convert dialogs, sending and
> converting stay enabled, customer-facing output unchanged (U7 `6d14b4ec`);
> workbench matrix badge, per-band toggle and "Confirm indicative rates (N)"
> (U8 `1df3d657`); docs, `CUTOVER.md` §5 row and `DRYRUN_LOG.md` Run 7 (U9).
> *Deferred, by decision:* customer-rendered caveats, stripping the flag from
> the Zoho payload, live recomputation on saved lines, booking-detail / owner /
> timeline surfaces, auto-confirm on price edit, confirming historical periods.

- **Severity:** 🟠 Gap (money-facing). The new system quotes carried-forward
  2027 rates exactly as if the owner had confirmed them; legacy flags them so
  staff know they are indicative. Nothing in the rebuild carries that flag,
  so the caveat is lost at cutover.
- **Source:** GAP-108 planning + dry run, ResProd (13-Aug-2026), re-measured
  2026-09-16. Deferred from GAP-108 by decision 5 ("load as normal, note in
  COVERAGE, follow-up ticket on indicative-rate display").
- **Files touched:** `pricing` models (a flag on the rate card or its rules),
  `data_migration/loaders/pricing.py` (`RatePlanLoader`/`RateBandLoader`),
  the quote surface (`pricing/services/engine.py` output and the SPA quote
  builder), `COVERAGE.md`, `CUTOVER.md` §5.

## What the flag means

When staff roll a villa's season forward they copy the previous season's rate
grid into the new one. `VillaSeason.CopyFrom` records the source season and
`CarriedRates = 1` marks the copy as **carried over, not confirmed by the
owner**. It is a staff-facing "treat this price as provisional" marker.

Measured on ResProd 2026-09-16 (live seasons, `DeletedAt IS NULL`):

| | |
|---|---|
| Seasons flagged `CarriedRates` | **198**, across **187** villas |
| …of which named "Season 2027" / "Low Season 2027" / "High Season 2027" | 175 |
| …named "Season 2026" | 23 |
| Every flagged season has a `CopyFrom` source | 198 / 198 |
| Live rate rows hanging off them (`DeletedAt IS NULL`, excluding `IsExTra`) | 8 137 |
| …dated today or later, i.e. **quotable** | **6 864** |
| Latest `ToDate` | 2028-06-03 |

So this is next season's price list for most of the portfolio, and it is
live in the quote engine.

## The problem

`RateBandLoader` reads `VillaSeasonRate` rows and ports them into the rate
grid; nothing reads `CarriedRates`, and the new model has nowhere to put it.
A 2027 quote therefore comes out of the engine indistinguishable from a 2026
quote built on owner-confirmed rates. The risk is not a wrong number — the
number is the one legacy holds — it is a **quote issued at a price nobody has
agreed to**, with no signal to the person sending it.

## Proposed fix

1. **Carry the flag.** The natural home is the rate card (`RateCard`, the
   season's analogue), not the individual rule — the flag is a property of
   the copied season. A nullable `rates_confirmed_at` is richer than a bool
   and answers "who confirmed, when"; a plain `is_indicative` is cheaper.
   Pick one and record it in `design/decisions.md`.
2. **Load it** in `RatePlanLoader`, with a transform test on a dict fixture,
   and a reconcile count so the 198 cannot silently become 0.
3. **Surface it.** A quote built wholly or partly from indicative rates says
   so — on the quote builder, and on anything that renders a price to a
   customer. Decide with the business whether an indicative quote may be
   *sent* at all, or only viewed internally; that answer belongs in
   `decisions.md` before the UI work starts.

## Acceptance

- The flag lands with a transform test and a reconcile check pinning it.
- The quote surface distinguishes indicative from confirmed pricing, per the
  recorded business decision.
- `COVERAGE.md` records `CarriedRates` as loaded rather than dropped, and
  `CUTOVER.md` §5 drops it from the expected-loss list.

## Dependencies

- Touches the same loader as SMELL-021 (price basis) and BUG-028's per-rate
  money columns; sequence after those rather than alongside, to keep the
  rate-grid diff readable.
- The display half needs the SPA quote builder, so it can land after the
  model + loader half.
