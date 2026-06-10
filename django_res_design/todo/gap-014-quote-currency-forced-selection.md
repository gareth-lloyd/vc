# GAP-014 — Quote builder forces currency selection; legacy prices each villa in its rate card's currency

- **Severity:** Gap (legacy-parity, customer/operator-facing behaviour) — design decision + tracker
- **Source:** 2026-06-10 investigation: legacy quote pages read from `ResSystem` branch
  `pinned-2025-04-03` (`QuoteGenerator.razor`, `RateLookup.razor`, `QuotationArgs.cs`,
  `sp_getQuotationData` / `sp_getQuotationPrices` in `Database/DbScript.sql`), a currency
  census of the legacy `VillaSeasonRate` table (24-Apr-2025 prod snapshot), and the new
  engine/builder code. Spec-provenance caveat per
  [GAP-010](gap-010-quote-enquiry-analyzed-wrong-codebase.md): the quote-screen specs were
  reverse-engineered from the post-deletion codebase, so the currency selector was never
  a legacy behaviour. Sibling of [GAP-005](gap-005-quotation-flow-parity.md) and
  [GAP-013](gap-013-quote-builder-ux-feedback-loops.md).
- **Files:**
  - `django_res/pricing/services/engine.py` — `_load_real_context` exact-matches
    `RatePlan.currency`; `currency` is a required input to `PricingEngine.quote()`
  - `django_res/pricing/views/quote.py:46,58` — `currency` required by both
    `/pricing:quote` and `/pricing:quote-bulk`
  - `django_res/reservations/models/quotation.py:65` — `Quotation.currency` is
    header-level; `QuotationLine` has **no** currency field
  - `frontend/src/features/quotations/components/QuoteBuilder.tsx` — forced currency
    `Select`, cart-wipe on currency change (`handleCurrencyChange`)
  - `frontend/src/features/quotations/api.ts` — `searchQuoteOptions` passes one
    currency for the whole batch
  - `frontend/src/features/quotations/components/QuoteResultsList.tsx` — single-currency
    display assumption

## Problem

**The rebuild forces an up-front currency selection and exact-matches it against
`RatePlan.currency`, with no FX conversion.** Property search has no currency filter, so
villas whose rate plans are in another currency come back from `/pricing:quote-bulk` as
`available: false` / `no_rate_available` — shown but unpriceable.

**Legacy has no currency input anywhere in the quote flow.** Verified on
`pinned-2025-04-03`:

- Neither `QuoteGenerator.razor` nor `RateLookup.razor` has a currency field in the
  search form; `QuotationArgs` has no currency property; `sp_getQuotationData` neither
  takes a currency parameter nor filters on `CurrencyId`.
- Each villa is returned priced in **its own rate card's currency**
  (`VM.SettingCurrencyId` / `VR.CurrencyId`); one results list freely mixes £/€/$
  (`RateLookup.razor` renders `{symbol}{price}` per row).
- Currency is persisted **per quote line**: `VillaQuotationDetails.CurrencyId`;
  `VillaQuotationMaster` (the header) has no currency column. A booking started from a
  quote line inherits that line's `CurrencyId`.

**The legacy data confirms operators never maintained per-currency rate cards.** Census
of `VillaSeasonRate` (non-deleted, non-extra; 304 villas with rates):

- 256 villas (84%) use exactly one currency — 248 EUR, 43 GBP, 9 USD overall.
- The 28 "multi-currency" villas are sequential currency *switches* across seasons
  (e.g. 2023 NULL → 2024 EUR → 2025 GBP), not parallel cards: only 18 overlapping
  different-currency rate-row pairs exist in the entire table, almost all from one
  villa's data churn.
- Hygiene noise the loaders already paper over: 3,824 rows across 154 villas have
  `CurrencyId IS NULL`, 21 rows have the invalid id `0`
  (`RatePlanLoader._resolve_property_currency` fallback chain).

**Consequence:** the currency dropdown partitions the portfolio. A GBP search marks
~85% of villas unavailable; the default EUR search silently breaks the GBP/USD villas.
This contradicts the "follow legacy for customer-facing" rule, and the schema departed
from legacy too (header-level `Quotation.currency`, no per-line currency) — which is
also what makes the [FG-001](fg-001-booking-quotation-currency-drift.md) drift possible.

## Proposed fix

Price in the rate card's currency, legacy-style. Drop the forced selection; currency
becomes an *output* of pricing, not an input to search.

1. **Engine.** Make `currency` optional in `PricingEngine.quote()`. When omitted,
   resolve the property's active `RatePlan` covering the dates regardless of currency;
   if plans in several currencies cover the range (rare — see census), pick
   deterministically: prefer the property's `PropertySettings.effective("currency")`,
   else latest `effective_from`. The quote result already carries its currency — verify
   and pin with a test.
2. **API.** `currency` becomes optional on `POST /pricing:quote` and
   `/pricing:quote-bulk` (kept for explicit-currency callers); each per-property result
   reports the currency it priced in.
3. **Schema.** Add `QuotationLine.currency` FK (legacy parity with
   `VillaQuotationDetails.CurrencyId`), populated from the engine result; manual lines
   get an operator-picked currency defaulting to the property's effective currency.
   Demote `Quotation.currency` to a nullable denorm/display default (or drop in a
   follow-up). This sharpens FG-001: a Booking created from a line inherits the
   **line's** currency — a cleaner invariant anchor than the header.
4. **Frontend.** Remove the forced currency dropdown and the cart-wipe on currency
   change (GAP-013 item 3 becomes moot — note it there when this lands); render each
   result and cart line in its own currency symbol. Mixed-currency carts are safe
   because the per-quote grand total was deliberately dropped (GAP-013 scope note) —
   nothing sums across lines.

Out of scope: FX-converted *display* pricing ("show this EUR villa in GBP") stays with
[Q-005](q-005-currency-display-base.md); bookings continue to price in the rate plan's
currency per `04-pricing.md`.

## Acceptance

- Engine test: a quote with no currency argument resolves the property's covering plan
  and returns that plan's currency in the result.
- Bulk-quote test over a mixed EUR+GBP fixture set: both price successfully — no
  `no_rate_available` caused purely by currency mismatch.
- `QuotationLine.currency` persisted from the pricing result; a booking created from a
  line carries the line's currency (FG-001 guard test).
- FE component tests: results list and cart render mixed currencies per-line; no
  currency selector required before search.
- Quality gate green (backend + frontend).

## Dependencies

- [GAP-010](gap-010-quote-enquiry-analyzed-wrong-codebase.md) — provenance: the
  selector came from the wrong-baseline analysis.
- [GAP-013](gap-013-quote-builder-ux-feedback-loops.md) — its item 3
  (currency-change confirm) is mooted by this ticket; coordinate.
- [GAP-005](gap-005-quotation-flow-parity.md) — flow tracker; this is a pricing/search
  parity slice of the same surface.
- [FG-001](fg-001-booking-quotation-currency-drift.md) — per-line currency is the
  natural place to anchor the booking↔quotation currency invariant.
- [Q-005](q-005-currency-display-base.md) — reports/FX normalisation is separate and
  unaffected.
- [Q-013](q-013-rate-card-incomplete-pricing.md) — incomplete-pricing contract shapes
  how "no covering plan in any currency" is reported.
