# GAP-007 — Changeover auto-shift dropped vs legacy (reinstate)

- **Severity:** 🟢 Gap / parity — **decision made (reinstate), ready to build.**
- **Source:** 2026-06-02 pricing audit; legacy `ResService.cs:2028-2041`. User
  directive to reintroduce the legacy behaviour (2026-06-02).
- **Files:**
  - `django_res/pricing/services/engine.py` (`quote()` per-night loop ~83-115; `_validate_card_against_stay` 257-277)
  - `django_res/pricing/services/quote.py` (`Quote` dataclass)
  - `django_res/pricing/models/changeover.py` (`ChangeOverRule`)
  - `django_res/pricing/models/rate.py` (`RateCard.changeover_weekday`)
  - design: `04-pricing.md` (engine "Steps"), `09-departures.md`, `10-decisions.md`

## Problem

Legacy silently advanced the arrival to the next valid changeover weekday before
pricing:

```csharp
// ResService.cs:2028-2041
if (item.SettingChangeoverDayId != -1) {
    while (selectedDay != item.SettingChangeoverDayId) {
        startDate = startDate.AddDays(1);
        selectedDay = (selectedDay == 6) ? 0 : selectedDay + 1;
    }
}
```

The rewrite instead **hard-rejects** a non-conforming arrival with
`ChangeoverViolation` (`engine.py:273-277`). That is an unflagged behaviour
regression: operators who relied on the silent nudge now get an error instead of
a quote on the corrected date.

## Decision (locked with the user)

Reintroduce the auto-shift. Chosen semantics:
- **Preserve the requested night count** — shift *both* `date_from` and `date_to`
  forward by the same delta (legacy kept `date_to` fixed and shortened the stay;
  we don't want a silently shorter stay).
- **Surface the shift** so the UI can show "adjusted to Saturday changeover".

## Proposed fix — code

- In `quote()`, before the per-night loop, add `_align_changeover(...)`:
  - Allowed-weekday set precedence: (1) `RateCard.changeover_weekday` if the
    resolved plan's active cards specify one consistently; else (2) the
    property's `ChangeOverRule` rows effective on `date_from` (many rows = allowed
    set; zero rows = any day — no shift). This mirrors legacy's property-level
    `SettingChangeoverDayId`.
  - If the set is empty or `date_from.weekday()` is already in it → no shift.
  - Else advance `date_from` to the next date (≤7 days) whose weekday is in the
    set; shift `date_to` by the same delta.
- Add `changeover_shifted_from: date | None` to the `Quote` dataclass + breakdown
  dict (`None` when no shift).
- `_validate_card_against_stay`: the `changeover_weekday` branch becomes the
  genuine-conflict backstop only — raise `ChangeoverViolation` solely when a card
  demands a weekday the property rule cannot satisfy (e.g. card=Sat, property
  allows only Mon). The common single-weekday case never reaches it.

## Acceptance

- Arrival off the changeover weekday shifts forward; nights preserved;
  `changeover_shifted_from` populated.
- Arrival already on a valid weekday → no shift, `changeover_shifted_from is None`.
- Property with zero `ChangeOverRule` rows → no shift.
- Genuine card-vs-property conflict → `ChangeoverViolation`.
- `04-pricing.md` step 2 documents the alignment + night-preservation rule +
  the `changeover_shifted_from` output; `10-decisions.md` records the reinstatement.

## Resolution

✅ Added `ChangeoverService.required_weekday` + `ChangeoverService.align_forward`
(pure shift, night-count preserving) in `properties/services/changeover.py`.
`PricingEngine.quote()` resolves the allowed weekday set (card `changeover_weekday`
if the active cards agree on one, else the property's effective day) and aligns
`date_from`/`date_to` before the night loop. `Quote.changeover_shifted_from`
(+ breakdown key) surfaces the original arrival. `_validate_card_against_stay`'s
existing `changeover_weekday` branch now runs on the shifted date as the
genuine-conflict backstop. Tests in `pricing/tests/test_engine.py`
(property-rule shift, card-weekday shift, no-shift-when-valid,
no-shift-when-no-rules, genuine card-vs-property conflict). Docs: `04-pricing.md`
step 1a, `09-departures.md`, `10-decisions.md`.

## Dependencies

- Sibling of [GAP-008](gap-008-no-rate-night-fallback-parity.md) (the other
  reinstated legacy leniency).
- Relates to [INV-002](inv-002-raterule-priority-tiebreak.md) (rule-pick
  tie-break, closed) — alignment runs *before* rule-picking, so it doesn't touch
  the tie-break.
