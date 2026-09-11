# GAP-108 — Quote builder cannot select opt-in extras (ported legacy extras are unquotable)

- **Severity:** 🟠 Gap (frontend). The catalogue exists; staff cannot use it.
- **Source:** GAP-107 plan review (2026-09-10). GAP-107 ports the 84 live
  legacy extras as **opt-in** `pricing.Extra` rows (`is_mandatory=False`,
  user decision), and the SPA quote builder has no way to opt one in.
- **Files touched (when built):**
  - `frontend/src/features/quotations/…` — the quote builder request payload
    never sends `opt_in_extras`.
  - `frontend/src/features/properties/rate-workbench/PriceProbePanel.tsx` —
    the only caller that does send `opt_in_extras` today (the pattern).
  - `django_res/pricing/services/engine.py` (`opt_in_extras` contract) — no
    backend change expected.

## Problem

The pricing engine applies a non-mandatory `Extra` only when the request
lists its pk in `opt_in_extras` (`pricing/services/engine.py`, GAP-076
contract). The rate-workbench price probe sends that list; the quote builder
never does. So every ported legacy extra — and every staff-created opt-in
extra — is catalogue + Zoho `extras[]` visibility only: a chef, a cot, an
extra-guest supplement can be seen but not added to a quote. Legacy staff
could add these from the villa's extras list when building a quotation.

## Proposed fix

- In the quote builder, list the property's active non-mandatory extras
  (already served by `GET /api/extras/?property=…`) as toggles per line,
  and pass the selected pks as `opt_in_extras` on the price request — the
  `PriceProbePanel` wiring, lifted into the builder.
- Persist the selection in the line's options the way the other per-line
  options are (note the `quotations/api.ts` field-by-field options rebuild
  from Q-018 — new option keys must be copied there).
- Show opted-in extras in the line breakdown / FinanceTab the way mandatory
  ones already appear.

## Acceptance

- A ported legacy extra (`legacy_id` set, `is_mandatory=False`) can be
  added to a quote line from the builder and appears in the engine
  breakdown and the saved line's snapshot. (vitest + one backend API test on
  `opt_in_extras` round-trip.)
- Mandatory extras are unaffected; a line with no opt-ins prices as today.

## Dependencies

- **GAP-107** (resolved 2026-09-10) — the catalogue this makes usable.
- GAP-076 (`commissionable`, `opt_in_extras` engine contract), Q-018
  (options rebuild gotcha).
