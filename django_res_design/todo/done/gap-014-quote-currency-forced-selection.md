> **✅ RESOLVED (2026-06-15)** — Problem: The quote builder forced a single currency selection. Fix: Made currency per-line end-to-end and dropped the header currency field.
>
> _Original ticket preserved below for context._

# GAP-014 — Quote builder forces currency selection; legacy prices each villa in its rate card's currency

- **Severity:** Gap (legacy-parity, customer/operator-facing behaviour) — design decision + tracker
- **Status:** ✅ **Implemented 2026-06-10** on `feat/gap-014-quote-currency` — all five
  steps landed (0: canonical currency resolution + loader fixes + audit command;
  1: engine currency optional; 2: API currency optional; 3: `QuotationLine.currency`,
  header field dropped, FG-001 re-scoped; 4: frontend selector removed, per-line
  currency throughout). Backend + frontend quality gates green.
- **Source:** 2026-06-10 investigation: legacy quote pages read from `ResSystem` branch
  `pinned-2025-04-03` (`QuoteGenerator.razor`, `RateLookup.razor`, `QuotationArgs.cs`,
  `sp_getQuotationData` / `sp_getQuotationPrices` in `Database/DbScript.sql`), a currency
  census of the legacy `VillaSeasonRate` table (24-Apr-2025 prod snapshot), and the new
  engine/builder code. Revised same day after critique (projection seam, migrated-data
  audit, FG-001 interplay, render path). Spec-provenance caveat per
  [GAP-010](gap-010-quote-enquiry-analyzed-wrong-codebase.md): the quote-screen specs were
  reverse-engineered from the post-deletion codebase, so the currency selector was never
  a legacy behaviour. Sibling of [GAP-005](gap-005-quotation-flow-parity.md) and
  [GAP-013](gap-013-quote-builder-ux-feedback-loops.md).
- **Files:**
  - `django_res/pricing/services/engine.py` — `_load_real_context` exact-matches
    `RatePlan.currency`; `currency` is a required input to `PricingEngine.quote()`
  - `django_res/pricing/services/projection.py` — `find_anchor_plan(property, currency, …)`
    is currency-keyed too; the lazy-projection fallback needs the same treatment
  - `django_res/pricing/views/quote.py:46,58` — `currency` required by both
    `/pricing:quote` and `/pricing:quote-bulk`
  - `django_res/reservations/models/quotation.py:65` — `Quotation.currency` is
    header-level; `QuotationLine` has **no** currency field
  - `django_res/reservations/services/bookings.py:72` — booking creation reads the
    **header** `quotation.currency`
  - `django_res/data_migration/loaders/pricing.py` — `_resolve_property_currency`
    falls back to `Currency.objects.first()` (ordering-dependent) for the
    NULL-currency legacy cohort
  - `reservations/serializers/quotation.py`, the quotation render/send seam
    (`SendPreviewDialog`, comms templates) — single-currency assumptions
  - `frontend/src/features/quotations/components/QuoteBuilder.tsx` — forced currency
    `Select`, cart-wipe on currency change (`handleCurrencyChange`)
  - `frontend/src/features/quotations/api.ts` — `searchQuoteOptions` passes one
    currency for the whole batch
  - `frontend/src/features/quotations/components/QuoteResultsList.tsx` —
    single-currency display assumption

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

- 256 villas (84%) use exactly one currency — 248 EUR, 43 GBP, 9 USD overall. EUR is
  the legacy system default (`VillaCurrency.IsDefault=1`).
- The 28 "multi-currency" villas are sequential currency *switches* across seasons
  (e.g. 2023 NULL → 2024 EUR → 2025 GBP), not parallel cards: only 18 overlapping
  different-currency rate-row pairs exist in the entire table, almost all from one
  villa's data churn.
- Hygiene noise: 3,824 rows across 154 villas have `CurrencyId IS NULL`, 21 rows have
  the invalid id `0`. (Census counts villas ever-rated; the currently-bookable mix is
  what determines practical severity — the audit below settles it.)

**Consequence:** the currency dropdown partitions the portfolio. A GBP search marks
~85% of villas unavailable; the default EUR search silently breaks the GBP/USD villas.
This contradicts the "follow legacy for customer-facing" rule, and the schema departed
from legacy too (header-level `Quotation.currency`, no per-line currency) — which is
also what makes the [FG-001](fg-001-booking-quotation-currency-drift.md) drift possible.

**Considered and rejected — keep single-currency-per-quote as a deliberate
simplification.** A customer comparing options across mixed currencies is awkward, and
an optional currency *filter* could paper over the partition. Rejected because: legacy
demonstrably mixed currencies in one quote (parity rule), the per-quote grand total was
already dropped (nothing sums across lines), and a filter still hides real inventory
from the operator. If mixed-currency quotes prove confusing in practice, the answer is
FX *display* conversion ([Q-005](q-005-currency-display-base.md)), not filtering.

## Proposed fix

Price in the rate card's currency, legacy-style. Drop the forced selection; currency
becomes an *output* of pricing, not an input to search.

**Canonical currency-resolution rule** (used by engine, projection, loaders, and
manual lines — one implementation, e.g. `pricing/services/currency.py`):

1. the property's other rate plans (most recent `effective_from` wins — after a
   currency switch this is the villa's *current* currency);
2. else `PropertySettings.effective("currency")`;
3. else **EUR** (the legacy system default; resolved by `code="EUR"`, never
   `Currency.objects.first()`).

### 0. Migrated-data audit + loader fix (prerequisite — do first)

Pricing in the plan's currency makes migrated `RatePlan.currency` customer-facing
truth, so the NULL-backfilled cohort must be verified *before* the engine change —
today a wrong currency is a loud `no_rate_available`; afterwards it would be a quote
in the wrong currency.

- Fix `_resolve_property_currency` in `data_migration/loaders/pricing.py` to apply the
  canonical rule above. For rule 1, infer from the same villa's **other non-NULL
  `VillaSeasonRate` rows** (most recent first) — the census shows NULL rows are mostly
  2023-era villas that later got real currencies. Kill the `Currency.objects.first()`
  fallback.
- Re-run the pricing loaders (idempotent) and add a `reconcile_legacy`-style check:
  every `RatePlan` whose legacy season had only NULL/0 `CurrencyId` rows must resolve
  through rules 1–2; count and list the rule-3 (EUR-default) remainder for manual
  sign-off. Report the currently-bookable currency mix while at it.

### 1. Engine

Make `currency` optional in `PricingEngine.quote()`. When omitted:

- `_load_real_context` looks for active plans covering the dates in **any** currency;
  if several currencies cover (rare — 18 overlapping rows in legacy), pick by the
  canonical rule (most recent `effective_from`, then settings currency).
- The **projection fallback gets the same treatment**: resolve the currency first via
  the canonical rule (most recent prior plan's currency — i.e. the villa's current
  currency, not a stale pre-switch one), then call
  `RateProjectionService.find_anchor_plan` with it.
- The quote result carries the currency it priced in — verify and pin with a test.

### 2. API

`currency` becomes optional on `POST /pricing:quote` and `/pricing:quote-bulk` (kept
for explicit-currency callers); each per-property result reports the currency it
priced in.

### 3. Schema — per-line currency; drop the header field outright

- Add `QuotationLine.currency` FK (legacy parity with
  `VillaQuotationDetails.CurrencyId`), populated from the engine result; manual lines
  get an operator-picked currency defaulting via the canonical rule (terminal EUR
  default — never blank).
- **Drop `Quotation.currency` in the same change** — not a nullable demotion. We are
  pre-cutover with no production data; a two-phase deprecation buys nothing and
  creates the null-ambiguity smell FG-002 already tracks. Fallout to handle in the
  same slice: `BookingService.create_from_quotation_line` (`bookings.py:72`) reads the
  line's currency instead; `BookingLoader`'s synthesised quotations; `seed_dev`
  factories; quotation serializers + frontend types.
- This **re-scopes FG-001**: its proposed header-equality constraint is obsolete. The
  invariant becomes *Booking.currency == source QuotationLine.currency* — update
  FG-001 to anchor there.

### 4. Frontend

Remove the forced currency dropdown and the cart-wipe on currency change (GAP-013
item 3 becomes moot — note it there when this lands); render each result and cart
line in its own currency symbol. If results are sorted by price, sort within currency
groups or drop numeric sort across mixed currencies (numeric sort across currencies is
meaningless). The send/preview path (`SaveQuoteDialog` → `SendPreviewDialog` and the
server-side quotation render) must render per-line currency — legacy quote emails
mixed currencies, so this is parity, not new behaviour.

Out of scope: FX-converted *display* pricing ("show this EUR villa in GBP") stays with
[Q-005](q-005-currency-display-base.md); bookings continue to price in the rate plan's
currency per `04-pricing.md`.

## Acceptance

- **Audit:** loader resolves the NULL-currency cohort via same-property rates →
  settings → EUR (test with dict fixtures per loader-test convention); reconcile
  output lists the EUR-default remainder; `Currency.objects.first()` is gone.
- Engine: a quote with no currency argument resolves the covering plan and returns its
  currency; with **two** covering plans in different currencies the canonical rule
  picks deterministically (test the tie-break).
- Projection: a currency-omitted quote for a future year anchors on the most recent
  prior plan and prices in *that* plan's currency (test a post-switch villa: GBP 2024
  → EUR 2025 anchors EUR for 2026).
- Bulk-quote over a mixed EUR+GBP fixture set: both price — no `no_rate_available`
  caused purely by currency mismatch.
- `QuotationLine.currency` persisted from the pricing result; a booking created from a
  line carries the **line's** currency (re-scoped FG-001 guard test).
- Render/send: a quotation with EUR + GBP lines renders each line in its own currency
  in the preview/email path (snapshot or component test).
- FE component tests: results list and cart render mixed currencies per-line; no
  currency selector required before search.
- Quality gate green (backend + frontend).

## Dependencies

- **Step 0 (audit + loader fix) gates steps 1–4** — do not ship rate-card-currency
  pricing against unaudited migrated currencies.
- [FG-001](fg-001-booking-quotation-currency-drift.md) — **must be re-scoped by this
  ticket** (header-equality fix obsolete; invariant moves to the line currency).
- [GAP-010](gap-010-quote-enquiry-analyzed-wrong-codebase.md) — provenance: the
  selector came from the wrong-baseline analysis.
- [GAP-013](gap-013-quote-builder-ux-feedback-loops.md) — its item 3
  (currency-change confirm) is mooted by this ticket; coordinate.
- [GAP-005](gap-005-quotation-flow-parity.md) — flow tracker; this is a pricing/search
  parity slice of the same surface.
- [Q-005](q-005-currency-display-base.md) — reports/FX normalisation is separate and
  unaffected.
- [Q-013](q-013-rate-card-incomplete-pricing.md) — incomplete-pricing contract shapes
  how "no covering plan in any currency" is reported.
