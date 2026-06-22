# SMELL-018 — Boot-time owner probe uses a 403 as control flow (console-error noise every staff session)

> **✅ RESOLVED (2026-06-20)** — Adopted Option 1. `OwnerMeView` relaxed from
> `IsOwner` to `IsAuthenticated`; an authenticated non-owner now gets
> `200 {user, is_owner: false, organisations: []}` (the not-owner branch reuses
> the already-listed `memberships`, predicate-identical to
> `owners.permissions.is_owner` — no extra query; the owner path drops 3→2
> queries). The SPA branches on `me.is_owner` instead of catching a 403:
> `ownerMeSchema.is_owner` relaxed `z.literal(true)` → `z.boolean()`, and
> `useOwnerMe` does `if (me.is_owner) setOwner else setNotOwner`, with any thrown
> error (5xx/network/parse, incl. a 403) now → retryable `error` rather than a
> false `not_owner`. No authz surface widens — the owner *data* endpoints
> (`/owner/properties`, …) keep `IsOwner`; the probe leaks nothing (empty orgs).
> A staff boot now logs zero console 403s. **Deviation from acceptance #?:**
> anonymous is rejected with **403** (not the ticket's stated 401) because this
> repo's `SessionAuth + BasicAuth` combo sets no `WWW-Authenticate` header under
> `IsAuthenticated`; it is still rejected, never a 200, so the intent holds.
> Option 2 (fold into `/auth/me`) and FG-009 left out of scope. Commits
> `d71cba5` (backend) + `89d6e9f` (frontend). Tests (TDD): `test_me_api` +
> `test_staff_api_isolation` flipped to the 200 not-owner contract (+ a new
> `/owner/properties` stays-403 pin); `ownerProbe`/`ownerHooks`/`schemas` FE
> tests assert not_owner from a 200 body and error from a 403. Backend `owners`
> 50 ✓, frontend 1128 ✓.

- **Severity:** 🟡 Smell (works correctly today; pollutes the console and will pollute prod error-tracking)
- **Source:** 2026-06-18 DEV frontend-observability sweep (Playwright + the query/render
  instrumentation layer) — first signal observed on `/dashboard` load.
- **Files:**
  - `frontend/src/app/boot.tsx:46` — `useOwnerMe(status === "authenticated")` probes for
    **every** authenticated user, staff included.
  - `frontend/src/features/owner-portal/hooks.ts:36-69` — `useOwnerMe`, `retry:false`;
    catches 401/403 → `setNotOwner()` (`:52`).
  - `frontend/src/features/owner-portal/api.ts:28-30` — `fetchOwnerMe` → `apiGet("/owner/me")`.
  - `django_res/owners/views/me.py:30` — `OwnerMeView.permission_classes = [IsOwner]`;
    docstring is explicit: *"authenticated staff-only users get 403 — the SPA uses that to
    pick its shell."*
  - `django_res/owners/urls.py:11`, `django_res/owners/permissions.py:37` (`IsOwner`).

## Problem

Owner-vs-staff shell selection is driven by the **HTTP status** of a boot-time probe. A
staff-only user is not an owner, so `GET /api/v1/owner/me` returns **403 by design**; the SPA
catches it and records `not_owner`. Functionally correct — but a 4xx is logged by the browser
at the network layer *before* JS sees it, so **every staff session prints a red
`Failed to load resource: 403 (Forbidden)` to the console**, and any prod error-tracker
(Sentry/Datadog RUM) will record one "error" per staff boot.

Cost:

- **Console noise** — drowns real errors during local debugging; the sweep above hit 5+ of
  these before any genuine signal.
- **Prod false positives** — an expected, non-error outcome is indistinguishable from a real
  authz failure in monitoring; alert fatigue / masking.
- **Coupling** — owner detection is wired to a specific status code. Suppression at the JS
  layer is *not* possible (the browser logs the network response regardless of how the promise
  is handled), so the fix has to change the contract, not the handler.

Note `useOwnerMe` already treats 401/403 as a terminal "not an owner" — the handling is right;
it's the *signalling channel* that's the smell.

## Proposed fix

Stop using an error status as a routing signal. Two options, smallest blast radius first:

1. **(Recommended) Make the probe a 200.** Relax `OwnerMeView` to `IsAuthenticated` and return
   `{ "is_owner": false, "organisations": [] }` for non-owners instead of 403 (owners keep the
   current `is_owner: true` + orgs/grants body). Frontend branches on `data.is_owner` instead of
   catching 403. Boot flow, store, and `RequireOwner` are otherwise unchanged. The owner *data*
   endpoints (`/owner/dashboard`, `/owner/properties`, …) keep `IsOwner`, so no authz surface is
   widened — the probe leaks nothing (empty orgs for a non-owner). Anonymous still 401s.

2. **Fold `is_owner` into `/auth/me`.** Add an `is_owner` boolean to the existing
   `UserMeSerializer` / `/auth/me` payload and route off that, dropping the second boot request
   entirely. The full org/grant detail still comes from `/owner/me`, but that call now happens
   only *inside* the owner portal (behind `RequireOwner`), where the caller is always an owner —
   so it never 403s in practice. Saves a round-trip but is a larger boot/guard refactor (the
   owner store is currently populated by the boot probe).

Either kills the console error. Prefer (1) unless we also want the round-trip saving of (2).

## Acceptance

- Authenticated **staff-only** user loads `/dashboard` → **zero** `403` entries in the browser
  console / network-error log; owner-vs-staff routing still correct.
- Authenticated **owner** still lands on `/owner/dashboard` with orgs/grants populated.
- Anonymous request to the probe endpoint still returns **401**.
- Backend test: non-owner authenticated `GET /owner/me` (option 1) returns `200` with
  `is_owner=false` and empty `organisations`; owner returns `is_owner=true` + orgs. (Write
  red-first — relaxing a permission class is easy to get subtly wrong.)
- FE test: `useOwnerMe`/boot records `not_owner` from a `200 {is_owner:false}` body (no longer
  depends on an `ApiError` being thrown).

## Dependencies

None. Related: **FG-009** (the other boot-time SPA-shell auth/CSRF footgun) — same surface,
natural to address together. Touches the same `UserMeSerializer` as `/auth/me` if option 2 is
chosen.
