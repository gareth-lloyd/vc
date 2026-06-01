# GAP-008 — No-rate-for-night fallback dropped vs legacy (reinstate)

- **Severity:** 🟢 Gap / parity — **decision made (reinstate), ready to build.**
- **Source:** 2026-06-02 pricing audit; legacy `ResService.cs:2150-2160`. User
  directive to reintroduce a fallback (2026-06-02).
- **Files:**
  - `django_res/pricing/models/rate.py` (`RatePlan` — new field + migration)
  - `django_res/pricing/services/engine.py` (per-night loop ~83-115; `winning_card` ~117)
  - `django_res/pricing/services/quote.py` (`QuoteLine`)
  - `django_res/pricing/serializers/rate.py`, `django_res/pricing/admin.py`
  - design: `04-pricing.md`, `09-departures.md`, `10-decisions.md`

## Problem

When no rate row covers a night, legacy quietly prices it at the villa's setting
price (`SettingNightlyPrice × 7`), so a villa with sparse rate rows still quotes:

```csharp
// ResService.cs:2150-2160  (priceObj == null path)
RatesModel calc = new() { WeeklyPrice = item.SettingNightlyPrice * 7, ... };
calc.Calculate();
weeklyPrice += calc.GrossPrice / 7;
```

The rewrite raises `NoRateAvailable` for any uncovered night (`engine.py:96-99`),
narrowing which villas can be quoted with no flagged decision.

## Decision (locked with the user)

Reinstate the fallback via an **explicit, opt-in, currency-scoped field** (not a
silent property-price echo).

## Proposed fix — code

- **Model:** add `RatePlan.fallback_nightly = DecimalField(max_digits=12,
  decimal_places=2, null=True, blank=True)`. `RatePlan` is the right home — it is
  already per-property + per-currency (legacy's `SettingNightlyPrice` was
  property-level, single-currency). `null` = no fallback → preserve today's hard
  error. New migration after `0005_*`; expose in `RatePlanSerializer` + `RatePlanAdmin`.
- **Engine:** when `pick_rule_for_night` returns `NoCoverage` (no rule covers the
  night at all): if `plan.fallback_nightly is not None`, append a synthetic
  `QuoteLine(date=night, rule_id=None, card_id=None, nightly=plan.fallback_nightly)`;
  else raise `NoRateAvailable` as today.
  - `OutOfRange` **still** raises `PartyOutOfRange` — fallback never masks a
    party-bracket miss (consistent with [SMELL-007](smell-007-occupancy-fallback-doc-claim.md)).
  - Make `QuoteLine.rule_id` / `card_id` `Optional[int]`; serialise `None` cleanly.
  - `winning_card`: if no night picked a real card (all-fallback stay), skip
    `_validate_card_against_stay` (no card to validate — mirrors legacy, which had
    no card concept on the fallback path). Otherwise unchanged.

## Acceptance

- `plan.fallback_nightly` set + a gap night → synthetic line at fallback, no raise.
- All-fallback stay → card validation skipped; quote returns.
- `fallback_nightly=None` + gap night → `NoRateAvailable` (unchanged).
- `OutOfRange` → `PartyOutOfRange` (unchanged).
- `04-pricing.md` documents the field + the `NoCoverage → fallback` step + the
  all-fallback card-skip; `10-decisions.md` records it; migration committed.

## Dependencies

- **Answers the pricing-engine half of [Q-013](q-013-rate-card-incomplete-pricing.md)**
  ("rate card incomplete for some nights"). Q-013's product question (flag
  "Incomplete pricing — manual quote" vs hide the villa) still stands for the UX;
  `fallback_nightly` is the engine mechanism when a fallback *is* desired.
- Sibling of [GAP-007](gap-007-changeover-autoshift-parity.md).
- Touches `RateRule`/`RatePlan` — coordinate with [BUG-002](bug-002-raterule-zero-length-range.md)
  / [BUG-003](bug-003-raterule-poa-vs-price-contradiction.md) if landing migrations together.
