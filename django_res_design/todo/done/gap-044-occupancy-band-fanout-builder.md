> **✅ RESOLVED (2026-07-01)** — The quote builder now fans out every covering
> occupancy band as its own default-checked, priced line the agent deselects.
> **Engine contract unchanged:** `PricingEngine.quote()` still resolves one band
> per call; a new read-only `PricingEngine.covering_bands(...)` enumerates the
> distinct `(min_party, max_party)` brackets on the card the engine would price
> for a week — party-independent, night-correct, mirroring `quote()`'s changeover
> shift, and empty unless the covering card carries ≥2 brackets.
> `StayOptionsService` attaches an `occupancy_bands` array to each
> `POST /quotations:search-options` result: each band is re-priced at its
> representative party (`max(1, min_party)`) reusing the loaded `PricingContext`
> (no per-band rate reload), POA/no-rate bands are flagged (`total:null`) not
> dropped, and bands are enumerated independent of the searched party so an
> out-of-bracket search still shows them (gated only on the week being
> date-available, not booked). The frontend renders the bands as a checkable
> priced list (default-checked; picker suppressed — bands price the default
> block only), carries the checked bands through the shortlist, and at save
> flat-maps each checked non-POA band into its own non-manual quotation line
> (`adults = max(1, min_party)`; the server re-prices the bracket). Bands are
> **alternatives**, never summed. Shipped backend `abf6bcd` (engine) + `d220f03`
> (service), frontend `1ca6b3b` (display) + `e28c6ea` (staging/shortlist/save).
> Deferred (unchanged): bands × alternate changeover blocks (default block
> only — **now resolved by GAP-044b / `gap-055-occupancy-band-week-picker.md`**),
> per-band manual override / discount, projection-year bands, a POA-only
> banded villa (operator uses a manual line). Cross-refs: `04-pricing.md`
> (fan-out default), `10-decisions.md`.

# GAP-044 — Quote builder: occupancy-band fan-out (all bands, default-checked)

- **Severity:** Gap (frontend + backend) — **reverses a prior pricing decision**
  (flagged below)
- **Source:** 2026-06-17 owner Loom ("we need occupancy-based pricing … each box
  could have different lines — 8–10 will be 120, 10–12 might be 140, 12–14 might
  be 160 … with additional checkboxes, checked by default … full visibility of
  what the price could be if the group size changes") + the mockup at
  https://vc-new-res-system.netlify.app/ → **Rate Lookup** (occupancy-priced
  properties carry an "Occupancy pricing" indicator).
- **Status:** Open.
- **Files:**
  - `frontend/src/features/quotations/QuoteResultsList.tsx`,
    `QuoteResultLine.tsx`, `QuoteShortlist.tsx`
  - `django_res/pricing/services/engine.py` (call per band) + a fan-out endpoint

## Problem

A property with occupancy-based pricing has several `RateRule` bands for the same
dates (e.g. 8–10 / 10–12 / 12–14 guests at different prices). The owner wants the
builder to show **all** bands for a week as separate lines, **checked by
default**, so the client sees the full price-by-group-size picture and the agent
deselects what's not wanted.

## Evidence note

The per-band-line layout is from the **Loom** (owner's explicit description); the
**mockup** only marks occupancy-priced properties with an "Occupancy pricing"
indicator and the demo villa rendered a single price line per week — the
multi-line breakdown was not directly observed. Treat the fan-out as the owner's
stated intent, to confirm the exact rendering during build.

## Tension to resolve (do not silently overwrite)

This **reverses** the current `04-pricing.md` decision that
`PricingEngine.quote()` resolves the *single* band for the party size and that
multi-band display is a *deliberate, selective* agent action — explicitly "not an
automatic fan-out" (rationale: per an earlier demo, agents quote selectively
rather than dumping every bracket). The owner now wants the opposite default:
fan out all bands, checked. Record the reversal in `04-pricing.md` and
`10-decisions.md`, **preserving the prior rationale as superseded by owner
(Loom 2026-06-17)**.

## Proposed fix

- **Engine unchanged in contract:** `PricingEngine.quote()` still resolves one
  band per call. The *builder* drives the fan-out by calling the engine once per
  band that covers the requested week (or a small `:bands` endpoint returns all
  covering bands' prices for a property + week).
- Render each band as its own checkable line within the week box
  ([GAP-043](gap-043-quote-builder-multi-week-range.md)), **checked by default**;
  unchecked bands are excluded from the quote.
- Respect `is_poa` bands and the incomplete-pricing flag
  ([Q-013](q-013-rate-card-incomplete-pricing.md)) — a band with no rate
  surfaces as manual, not silently dropped.

## Acceptance

- For an occupancy-priced property, each covering band shows as a default-checked
  line with its own price; deselecting excludes it from the quote.
- The engine's single-band resolution contract is unchanged (the builder fans
  out); `04-pricing.md` + `10-decisions.md` record the reversal with prior
  rationale retained.
- Quality gate green.

## Dependencies

- [GAP-043](gap-043-quote-builder-multi-week-range.md) (bands render inside the
  week boxes). Spec amendments: `04-pricing.md` (fan-out decision),
  `10-decisions.md`. Related: [BUG-009](../bug-009-price-basis-ignored-by-engine.md)
  (price_basis) touches the same engine path.
