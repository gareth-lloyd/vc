# GAP-080 — Make currency unmistakable in the quote builder UI

> **✅ RESOLVED (2026-07-11)** — new `formatMoneyWithCode` formatter
> (`frontend/src/lib/format/money.ts`) renders the ISO code explicitly for
> every currency ("£4,500.00 GBP"; CHF not duplicated; unmapped codes already
> trailed; "—" fallback undecorated), swapped into all 8 quotations-feature
> money-display sites: builder (`QuoteShortlistLine`, `QuoteResultLine`) plus
> saved-quote detail (`QuotationLineCard`) and `ConvertQuotationDialog`.
> Shared `withCurrency`/`formatMoney` untouched (app-wide blast radius).
> ~50 test assertions updated/strengthened incl. previously-vacuous substring
> regexes and a first money assertion for the convert dialog. Email templates
> unchanged (already print codes). Deferred: currency grouping → GAP-078;
> enquiry-rail `EnquiryQuoteStack` stays symbol-only. Commits
> f957bcb/48f39f0/f72ae0c.

- **Severity:** 🟢 Gap (FE polish). Frontend-only.
- **Source:** 2026-07-08 Nick / Gareth res-rebuild call. Nick: a quote can mix
  property base currencies; clients "assume everything's in euros" and get a
  surprise on a GBP villa — wants the currency made **very obvious**, not just a
  symbol. *(Note: the quote **email** already prints the ISO code before every
  amount; this ticket is the **builder UI**, where it's symbol-only.)*
- **Files touched (best-guess):**
  - `frontend/src/lib/format/money.ts` — `withCurrency` (~L66-69) shows the bare
    symbol for mapped GBP/EUR/USD and appends the ISO code **only** for unmapped
    currencies; `SYMBOLS` map (~L1-9).
  - Builder callers: `QuoteShortlistLine.tsx` (~L88/121/230),
    `QuoteResultLine.tsx` (~L401/506/529) — comments there already note a single
    list mixes £/€/$.
  - Email is already correct:
    `django_res/comms/templates/comms/quotation.sent.body.mjml` (~L32) and
    `django_res/reservations/templates/reservations/quotation_quote.html`
    (~L60-61) print `{{ line.currency_code }} {{ line.total }}`.

## Problem

In the builder, GBP/EUR/USD render as bare symbols; a mixed-currency quote gives
no strong signal of which currency a line is in. GAP-026 added a currency
adornment/mismatch warning on rate fields, but the quote-builder totals are still
symbol-only.

## Proposed fix

- Surface the ISO code alongside amounts in the builder for **all** currencies
  (e.g. `£1,234 GBP`, or a per-line/per-group currency chip), not only unmapped
  ones — either by changing `withCurrency` for the builder callers or via a
  builder-specific formatter — so mixed currencies are unmistakable.
- Optionally group/label lines by currency (dovetails with GAP-078 country/region
  grouping, since currency tracks country).

## Acceptance

- Each priced line in the builder shows its currency code, not just a symbol; a
  mixed-currency shortlist is visually unambiguous. (component test)
- The email output is unchanged (already shows codes).
- Quality gate green (FE).

## Dependencies

- Complements **GAP-026** (currency display beside money fields, done) and
  **GAP-014** (per-line currency, done).
- Pairs with **GAP-078** (grouping by country/region ≈ by currency).
