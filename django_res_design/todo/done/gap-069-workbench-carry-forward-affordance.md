> **✅ RESOLVED (2026-07-03)** — Problem: the carry-forward endpoint (promote a
> projected future year into editable rate rows) was built and tested but had no
> caller in the SPA — only a Django-admin action reached it. Fix: frontend-only.
> Added the data layer (`carryForwardRatePlan` + `useCarryForwardRatePlan`) and a
> `CarryForwardDialog`, wired into the rate workbench's "Nothing scheduled in
> {year}" empty state: a writer-gated "Carry rates forward" button (offered only
> when the active plan has a resolvable currency code and the target year isn't
> in the past), with an optional uplift %. On success the new plan is selected
> and the year fills in place. **No backend change** — endpoint, service,
> permission, idempotency and 20-year guard already shipped. Landed on local
> main (ff, unpushed): `f524142` (data layer + dialog), `e303050` (wiring),
> `62f5f14` (Greek i18n parity). Deferred as scoped: `date_map` selector,
> `allow_projection` opt-out, negative uplift/reductions, naming the anchor year.
>
> _Original ticket preserved below for context._

# GAP-069 — Explicit carry-forward has no workbench affordance; the endpoint is unreachable from the SPA

- **Severity:** 🟠 Gap (designed surface — the service, endpoint, and admin
  action all exist and work; the staff-facing SPA has no button that calls
  them)
- **Source:** 2026-07-03 far-future-rates investigation (owner-feedback pass)
- **Files:**
  - `pricing/services/carryover.py` (`RateCarryoverService.materialise()`,
    `:103–245`) — clones an anchor year into **editable**
    `RatePlan`/`RatePeriod`/`RateBand` rows; idempotent per
    `(property, currency, target_year)`; reuses projection's date-map + uplift.
  - `pricing/views/rate.py:96–151` (`PropertyRatePlanCarryForwardView`) —
    `POST /properties/{id}/rate-plans:carry-forward`, body
    `{"currency","target_year","uplift_pct?"}`, `permission_classes =
    [IsReservationsWriter]`, 20-year window guard (`:133`), `NoRateAvailable`
    → 409. **Fully functional, zero SPA callers.**
  - `pricing/urls.py:47–49` (route name `property-rate-plan-carry-forward`).
  - `pricing/admin.py:55–68` (`carry_forward_next_year` Django-admin bulk
    action — the *only* UI entry point today, and it's the admin site, not the
    React staff tool).
  - FE (read-only projection surfaces, present and correct — the *display*
    half is done): `frontend/src/features/rate-workbench/components/QuoteResultCard.tsx:75`
    (projected badge), `frontend/src/features/availability/components/TimelineGrid.tsx:127`
    (guide-value marker), `frontend/src/features/quotations/components/QuoteResultLine.tsx:446`.
  - FE (the gap): **no** occurrence of `carry-forward` / `carryover` /
    `materialise` / `allow_projection` anywhere under `frontend/src`.
  - Natural home for the new affordance: `frontend/src/features/rate-workbench/`.

## Problem

The projection subsystem is **display-complete but control-incomplete.** Lazy
projection (`pricing/services/projection.py`) quotes any future year off the
most recent prior year and the SPA renders the "Projected rates" / guide-value
markers everywhere a quote appears. But the *second act* of the design —
staff **promoting** a projected year into editable rows once the owner returns
real numbers (optionally with an uplift) — is only reachable via:

1. a Django-admin bulk action (`carry_forward_next_year`), or
2. a hand-rolled REST call to `…:carry-forward`.

The staff who would actually run it work in the **rate workbench**, which has
no button for it. So in practice a projected year stays a guide forever, or
someone drops into Django admin. The `uplift_pct` parameter — "carry 2026
forward at +5%" — is not expressible from the SPA at all.

## Why it bites

- The workbench already *knows* when it is looking at a projected year (it
  renders the badge) — that is precisely the moment the user needs the
  "make these real / hand-tune them" action, and it isn't there. The feature
  reads as broken-in-half: the system tells you it's a guide but gives you no
  in-tool way to firm it up.
- Backend cost is ~zero — the endpoint, service, permission, idempotency, and
  year-guard are all built and tested. This is a missing frontend affordance on
  top of a live endpoint, not new backend surface.

## Proposed fix

Add a carry-forward affordance to the rate workbench, shown when the workbench
is scoped to a `(property, currency, year)` that has **no real plan** (i.e. the
probe/timeline is `is_projected`):

- An action — e.g. **"Carry {source_year} → {target_year} as editable rates"** —
  with an optional **uplift %** field (default 0 = verbatim), calling
  `POST /properties/{id}/rate-plans:carry-forward` with
  `{currency, target_year, uplift_pct}`.
- On 201, refetch the plan/period/band queries for that year so the workbench
  flips from projected-guide to real-editable in place; surface the returned
  `RatePlanDetailSerializer` plan as the newly active scope.
- On 409 (`NoRateAvailable` — no prior year to carry from) show the
  "no rates to carry" empty state rather than a generic error.
- Respect `IsReservationsWriter`: hide/disable the action for viewers.

Out of scope (call out, don't build): a `date_map` selector — the endpoint
uses the service default (`shift_to_changeover_weekday`) and the map choice is
still an open business decision (see `10-decisions.md` "Carryover date-mapping
rule", pending Bryony's listing Loom). Ship the button against the default;
add a selector only once that decision lands.

## Acceptance

- Rate workbench, scoped to a projected future year, shows a carry-forward
  action with an uplift field; a viewer role does not.
- Clicking it POSTs to `…:carry-forward` and, on success, the workbench shows
  the now-real editable rows for that year without a full reload.
- A vitest covers: action visible only when `is_projected` + writer role;
  success path refetches; 409 renders the no-prior-rates state.
- No backend change required (note explicitly in the closing commit if one
  turns out to be needed).

## Dependencies

- Sibling to the same investigation's **`allow_projection` question**: whether
  per-villa projection opt-out becomes a `PropertySettings` policy is a
  *separate, demand-driven* decision and is **not** part of this ticket — this
  is purely the carry-forward button. (The booking `allow_projection=False`
  guard stays an unconditional server-side invariant regardless.)
- Related: **Q-018** (rate-reduction base/reduction split) — same carryover
  service; if Q-018's field-shape change lands first, the uplift semantics this
  button exposes should match. Not a hard blocker.
- Related: **Q-022** (seasons-defined-by-rates) and the `effective_from`/
  `effective_to`-vs-period-coverage seam noted in the same investigation — the
  carryover path is where a plan's envelope gets written, so it's the natural
  place to establish an "envelope follows period extents" invariant if that
  work is taken up. Cross-reference, not a dependency.
