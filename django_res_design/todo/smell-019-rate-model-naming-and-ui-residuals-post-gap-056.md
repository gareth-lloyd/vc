# SMELL-019 — Rate-model naming & UI residuals after the GAP-056 restructure

- **Severity:** 🟡 Smell / debt (naming lag + one dropped UX affordance). No
  wrong-money-out, no structural risk — the [GAP-056](done/gap-056-rate-model-restructure-property-period-band.md)
  restructure is complete and verified end-to-end. These are the deliberately
  **deferred** cosmetic/rename items and one intentionally-removed helper, parked
  here so they aren't lost.
- **Source:** GAP-056 close-out review (2026-07-01). The restructure moved
  date ownership from `RateRule` onto a new `RatePeriod` and dropped `RateCard`,
  but — to keep the diff localised and every commit green — several names and one
  UI helper were left lagging the new model on purpose (see GAP-056 plan
  "Key decisions" #1 and #7, and Unit 8's review).

## Residual 1 — `RateRule` is now a pure party band; the name lags

`RateRule` no longer carries dates or a card — it is exactly a party band
(`min_party`/`max_party` + `nightly`/`weekly`/`is_poa`/`is_approved`) hanging off
a `RatePeriod`. The honest name is `RateBand`. GAP-056 **kept `RateRule`** on
purpose: ~55 consumers treat it as *the priced thing* and its `rule_id` is
embedded in the `QuotationLine.pricing_snapshot` JSON (plain ints, no FK), so a
rename is a wide, low-value churn best done as its own pass.

- **Cost of leaving it:** every new reader has to learn "a Rule is really a band."
- **If actioned:** rename model + FK + serializer fields + the snapshot key
  (`rule_id` → `band_id`, with a back-compat read for historical snapshots) plus
  the ~55 consumers. Mechanical but broad; do it in one dedicated commit, not piecemeal.
- **Files:** `pricing/models/rate.py` (`RateRule`), `pricing/serializers/rate.py`,
  `pricing/services/quote.py` (`pricing_snapshot`), and grep `RateRule`/`rule_id`.

## Residual 2 — `/seasons` route + `RatePlan` naming vs the new `RatePeriod`

The API still calls a `RatePlan` a "season" (`properties/{id}/seasons`,
`seasons/{pk}`, `seasons/{season_id}/rate-periods`) — but "season" (a dated
window) is now conceptually the **`RatePeriod`**, while a `RatePlan` is really a
per-currency *rate sheet*. GAP-056 deliberately kept `/seasons` to avoid route
churn (plan decision #7). The nested shape `seasons/{season_id}/rate-periods` now
reads awkwardly ("periods under a season").

- **Cost of leaving it:** the route vocabulary contradicts the model vocabulary;
  `season_id` in the URL is a `RatePlan` pk.
- **If actioned:** rename to `/rate-plans` (or `/plans`) with a redirect/alias
  window; update the FE `api.ts` route builders + query keys in lockstep.
- **Files:** `pricing/urls.py` (42–62), FE `features/properties/api.ts` +
  `features/rate-workbench/*` route builders.

## Residual 3 — GAP-025 changeover-aware end-date suggestion was removed, not relocated

[GAP-025](done/gap-025-changeover-aware-rate-band-dates.md) shipped a
`suggestRateBandEnd` helper that auto-filled a rate **band's** end date to the
next changeover weekday (Sat→Fri) as you typed the start. GAP-056 Unit 8 **deleted
that helper** (and its 6-test suite) as dead code, because bands no longer own
dates — dates moved to the period, and `RateRuleFormDialog` is now party+price
only. The auto-fill was **not reinstated** on the new `RatePeriodFormDialog`
(which owns the dates now).

- **Net effect:** the changeover-aware end-date convenience from GAP-025 is
  currently gone from the rate editor. Periods are seasonal (often not changeover-
  aligned), so it may be genuinely unwanted at the period grain — but this is a
  **product call**, not an obvious fix, so it's recorded rather than actioned.
- **Decision needed:** either (a) confirm the affordance is intentionally dropped
  at the period grain and mark GAP-025 as "helper retired by GAP-056", or
  (b) reinstate changeover-aware date suggestion on `RatePeriodFormDialog`.
- **Files:** `frontend/src/features/properties/components/RatePeriodFormDialog.tsx`;
  changeover data already surfaces in the workbench ("Changeover" lane).

## Non-issue (recorded so review doesn't re-raise it)

- **`RatePeriod.is_active` backfill artifact:** the one-time expand migration
  (`0013`) stamps every backfilled period `is_active=True` regardless of the
  now-dropped `RateCard.is_active`. **Zero prod impact** — the full 36 MB dump has
  0 multi-card villas and no inactive cards, so no active rate was ever gated by a
  card's inactivity. Nothing to do; noted only to close the loop.
