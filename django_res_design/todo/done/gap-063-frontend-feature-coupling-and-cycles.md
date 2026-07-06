# GAP-063 — Frontend feature boundaries leak: cross-feature imports + schema-level cycles, no enforced module contract

> **✅ RESOLVED (2026-07-05)** — six units on local main (80f5004…73b376d).
> `eslint-plugin-boundaries` now bans feature→feature imports outside the
> shrink-only `ALLOWED_EDGES` ratchet (`frontend/boundaries.allowlist.js`,
> 32 → 27 pairs), with a vitest staleness guard
> (`src/test/boundaries.test.ts`) that fails when a paid-down edge's entry
> lingers. rate-workbench folded into `features/properties/rate-workbench/`
> (disposition recorded in `frontend/CLAUDE.md`). All four 2-cycles named
> below are broken: properties⇄availability (geo hooks moved home),
> enquiries⇄quotations (read-model → `src/lib/domain/quotation.ts`),
> contacts⇄enquiries (status enums → `src/lib/domain/statuses.ts`),
> auth⇄owner-portal (logout-cleanup registry in `src/lib/auth/`, run on both
> logout and expiry-401). `src/lib/domain/` is the landing zone GAP-062's
> shared money/country schemas should join.

- **Severity:** Gap (frontend architecture) — the module boundaries exist by
  convention but nothing enforces them, so they are eroding.
- **Source:** the 2026-07-02 frontend complexity audit (cross-cutting /
  coupling).
- **Files:**
  - `frontend/src/features/rate-workbench/*` (26 imports into
    `features/properties` — schemas, api, hooks, `periodLabel`, `coverage`,
    `CurrencyPicker`, `RateBandFormDialog`, `RatePeriodFormDialog`,
    `ServiceFormDialog`).
  - `frontend/src/features/enquiries/schemas.ts:4` (imports
    `quotationDetailSchema`) ⇄ `features/quotations/*` (imports `EnquiryDetail`
    in ~5 places) — schema-level cycle.
  - `frontend/src/features/availability/schemas.ts:2,5`,
    `availability/status.ts:1` (import from `properties`) ⇄
    `properties/PropertiesListPage.tsx:24` (imports `useRegions` back) — cycle.
  - `frontend/src/features/contacts/schemas.ts:4–6` (pulls booking/enquiry/
    company status enums), `auth/hooks.ts:3` (imports `useOwnerStore` from
    owner-portal) ⇄ owner-portal (imports auth store/hooks).
  - No import-linter equivalent in the frontend (backend has one; see FG-013).

## Problem

`features/*` reads as a set of independent modules, but the import graph shows
them fused. Weighted feature→feature edges (production code, excluding tests):

| edge | imports |
|---|---|
| rate-workbench → properties | 26 |
| properties → contacts | 8 |
| availability → properties | 8 |
| properties → admin | 7 |
| enquiries → contacts | 6 |
| quotations → enquiries | 5 |

- **`rate-workbench` is not a real module.** It reaches into `properties` for
  data, formatting, pickers and three FormDialogs; it cannot be extracted,
  moved, or reasoned about without dragging `properties` along. It is
  effectively a `properties` sub-feature wearing its own directory.
- **Schema-level circular dependencies.** `enquiries ⇄ quotations` and
  `properties ⇄ availability` import each other's **schemas** — coupling the
  data models, not merely UI. These are the stickiest kind: you cannot touch
  one feature's response shape without a chance of a compile ripple in its
  cycle-partner, and neither can be lifted out or lazy-split cleanly. `auth ⇄
  owner-portal` and `contacts ⇄ enquiries` are lighter but the same shape.

Nothing is broken today. But every one of these edges is a future
"why can't I move / delete / test this feature in isolation?" — and with no lint
rule guarding the boundary, the count only grows. Designed-but-unenforced module
structure → Gap.

## Proposed fix

Not a big-bang refactor. Establish the contract, then pay down opportunistically:

1. **Add an `eslint-plugin-boundaries` (or import/no-restricted-paths) rule**
   that bans `features/X` importing `features/Y` — allowed cross-feature code
   must move to `src/components/` (shared UI), `src/lib/` (shared logic/schemas),
   or an explicit public `features/Y/index.ts` barrel. Ratchet: allowlist the
   current edges so CI stays green, then remove entries as they're fixed (the
   backend import-linter model, FG-013).
2. **Break the two schema cycles first** (highest structural payoff): lift the
   shared shapes — the enquiry/quotation cross-refs and the property/availability
   cross-refs — into `lib/` or a neutral `features/shared` so neither side
   imports the other. Pairs with the shared-schema work in
   [GAP-062](gap-062-frontend-schema-contract-drift-no-codegen.md).
3. **Decide rate-workbench's status:** either fold it into `features/properties`
   (accept it's a sub-feature and stop pretending), or invert the dependency by
   promoting the shared pieces (`periodLabel`, `coverage`, the rate FormDialogs,
   `CurrencyPicker`) into shared locations so both consume them as peers. Given
   26 edges, folding is likely the honest call.

## Acceptance

- An eslint boundary rule is active; the current cross-feature edges are an
  explicit, shrinking allowlist (not silently permitted).
- `enquiries ⇄ quotations` and `properties ⇄ availability` no longer import each
  other's `schemas.ts` (verified by `grep` / the boundary rule).
- rate-workbench's disposition is decided and recorded in `frontend/CLAUDE.md`
  (folded, or the shared pieces relocated with the allowlist entry removed).
- Quality gate green.

## Dependencies

- Shares the shared-schema extraction with
  [GAP-062](gap-062-frontend-schema-contract-drift-no-codegen.md); do the
  `money`/`country`/status-enum lift once and let both tickets consume it.
- Frontend analogue of backend [FG-013](done/fg-013-owners-app-outside-layers-contract.md)
  (import-linter) — same "enforce the layering you already believe in" idea.
