> **✅ RESOLVED (2026-06-18)** — Added a pure `suggestRateBandEnd(dateFromIso,
> changeoverDay, minNights)` helper (`frontend/src/lib/format/date.ts`): the day
> before the next changeover weekday at least `minNights` out, always strictly
> after `date_from` (so it satisfies the rule's `date_to > date_from` check).
> `RateRuleFormDialog` watches `date_from` and fills `date_to` while empty/unedited
> — never clobbering a typed value, never in edit mode. `SeasonDetailPanel` sources
> `changeover_day`/`min_nights_rental` via `usePropertySettings(propertyId)` (newly
> threaded from `PricingTab`) and passes them to the create-mode dialog. No
> suggestion when changeover is `"any"`/unset. Vitest covers the date maths
> (week wrap, `minNights > 7`, `"any"`/unset, unparseable input) and the dialog
> wiring (fills, no-clobber, `"any"`-skips).
>
> _Original ticket preserved below for context._

# GAP-025 — Changeover-aware rate-band end-date suggestion

- **Severity:** Gap (UX; the loader's single most-repeated irritation)
- **Source:** 2026-06-11 new-villa setup transcript review
- **Status:** Pulled into the **add-property-flow** cluster — cheap,
  pure-frontend, zero migration, and shares the rate-entry surface with the
  rest of that work.
- **Confirmed:** The 2026-06-11 email thread confirmed this is wanted — "rate
  band dates will follow the changeover pattern, so a Saturday-arrival villa
  suggests Saturday-to-Friday automatically", welcomed by the customer.
- **Files:**
  `frontend/src/features/properties/components/RateRuleFormDialog.tsx`
  (~line 117, "Save and Add Another" date_from auto-fill),
  `properties/models/settings.py` (`changeover_day`, `min_nights_rental`)

## Problem

In legacy, after saving a rate band the next band's dates are generated
with a bare `.AddDays(7)` (`ResSystem/.../Rates.razor`), so for a
Saturday-arrival villa the suggested end lands on a Saturday and she
corrects it to Friday on **every band, every season** ("it would be useful
if it could go Saturday to Friday… when it's automatically generating
these dates").

The new `RateRuleFormDialog` already half-fixes this: "Save and Add
Another" sets the next `date_from = previous date_to + 1`. But `date_to`
is still typed by hand for every band.

## Proposed fix

When the property has `changeover_day` set (and optionally
`min_nights_rental`), suggest `date_to` as the day before the next
changeover at least `min_nights` out — e.g. Saturday changeover, 7-night
minimum, `date_from` Sat 4 Jul → suggested `date_to` Fri 10 Jul. The
suggestion pre-fills the input but stays editable (bands longer than one
week are common — she enters month-long bands). With
`changeover_day = ANY`/unset, keep current behaviour.

Pure frontend change; the settings fields already exist and are exposed.

## Acceptance

- For a Saturday-changeover property, "Add rule" / "Save and Add Another"
  pre-fills a Fri `date_to`; user can override freely.
- No suggestion when changeover is ANY/unset.
- Vitest cover for the date maths (changeover wrap, min-nights > 7).

## Dependencies

None. Related: GAP-007 (changeover auto-shift in the pricing engine,
already resolved — this is the editor-side counterpart).
