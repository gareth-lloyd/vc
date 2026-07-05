> **✅ RESOLVED (2026-07-05)** — shipped as 5 units on `feat/bug-018-cache-invalidations`
> (7ea9f07, 0af438c, 732ba91, df69b90, 72f20e0). New entity→dependents map at
> `frontend/src/lib/query/invalidate.ts`; booking/quotation/enquiry mutations route
> through it (availability + contact sub-tabs now refresh); properties
> over-invalidation narrowed. Two deliberate deviations from this ticket's text:
> (1) booking payloads carry no contact FK (GAP-045), so booking mutations use the
> broad `["contacts","detail"]` prefix (user-approved; precise targeting would need
> a backend `person` field — revisit if noisy). (2) The prescribed
> `properties.features(id)` invalidation was wrong for the as-built code — nothing
> subscribes to that key; `feature_ids` ride the detail payload — so the features
> save writes its response into `properties.detail(id|slug)` via setQueryData
> instead (same narrowing goal, no staleness).

# BUG-018 — Frontend cache staleness: booking mutations skip the availability calendar; contact sub-tabs never invalidate

- **Severity:** 🔴 Bug (frontend) — a mutation succeeds but leaves other
  surfaces showing stale, contradictory data to the operator.
- **Source:** the 2026-07-02 frontend complexity audit (React Query
  invalidation layer).
- **Files:**
  - `frontend/src/features/bookings/hooks.ts:172–179` (`onActionSuccess`),
    `:206` (`useModifyBookingDates`), `:384` and the
    `invalidateChargeDependents` / `invalidateRefundDependents` /
    `invalidateSecurityDepositDependents` fan-out helpers.
  - `frontend/src/features/quotations/hooks.ts:191` (`useConvertQuotation`),
    `:227–230` (`invalidateAfterHoldChange`, the correct model to copy).
  - `frontend/src/features/contacts/hooks.ts:102` (only the contact edit path
    invalidates `contacts.detail`).
  - `frontend/src/lib/query/keys.ts:36–78` (key tree — `properties.*` and
    `contacts.*` sub-resources hang off the `detail` prefix).

## Problem

Query keys are well-centralised (`keys.ts`), but every mutation **hand-lists**
the keys it invalidates, with prose comments justifying each inclusion/omission.
The list has drifted out of sync with reality and now ships two concrete
staleness bugs plus a latent refetch-storm.

- **Booking lifecycle & money mutations never touch the property availability
  calendar.** `onActionSuccess` (`bookings/hooks.ts:172–179`) invalidates the
  booking detail, lists, status-counts and dashboard — but never
  `properties.availabilityRoot` / `holdsRoot` / `bookingsInRange` /
  `availability.all()`. So `useModifyBookingDates` (`:206`) moves a booking's
  dates yet the property month grid, the multi-villa timeline, and the
  property's bookings-in-range all keep showing the **old** dates until
  `staleTime` lapses. Confirm / cancel / decline / archive share the gap. The
  fix pattern already exists three lines away in quotations: a hold change
  *does* invalidate `availability.all()` (`quotations/hooks.ts:227–230`) — the
  coupling is understood, just inconsistently applied.

- **Contact detail sub-tabs are permanently stale.** Nothing outside the
  contacts feature ever invalidates `contacts.bookings` / `contacts.enquiries`
  / `contacts.properties` (`keys.ts:75–77`). Confirming/cancelling a booking,
  sending/converting a quotation, or editing an enquiry never refreshes the
  contact's Bookings / Enquiries / Properties tabs — they keep the pre-mutation
  snapshot. (`contacts/hooks.ts:102` invalidates `contacts.detail`, which is a
  prefix that *would* cascade to the sub-tabs — but it only fires on a contact
  edit, not on the cross-entity mutations that actually change those lists.)

- **`useConvertQuotation` skips the parent enquiry.** `useSendQuotation`
  invalidates `enquiries.detail` / `enquiries.activity`; convert creates a
  booking and flips the enquiry status but invalidates neither (nor the
  contact's bookings tab).

## Why it's a bug (not a smell)

The operator sees wrong data *today*: a moved booking still renders at its old
dates on the calendar an operator uses to decide availability; a customer's 360
profile shows a booking count / history that contradicts what just happened.
"UI asserts a state the backend no longer holds" is the bug bucket. (The
sibling over-invalidation below is merely wasteful, but it is masking this class
by accident — see the note.)

## Proposed fix

- **Stop hand-listing keys per mutation.** Introduce a small
  entity→dependents invalidation map (e.g. `invalidateBookingDependents(qc,
  booking)` that knows a booking touches: its own detail/lists/status-counts +
  dashboard + the owning property's availability/holds/bookings-in-range + the
  linked contact's `detail` subtree). Route `onActionSuccess`, the modify
  paths, and the charge/refund/SD fan-out helpers through it. One place to add
  a surface when a new one appears — the thing the current per-hook lists keep
  forgetting.
- Have `useConvertQuotation` and the quotation send/hold paths invalidate the
  parent enquiry **and** the linked contact subtree.
- **Fix the over-invalidation while here (sibling smell).**
  `invalidatePropertyDetail` and `useUpdatePropertyFeatures`
  (`properties/hooks.ts:734–777`) invalidate `properties.detail(id)`, which is
  a *prefix* of every property sub-resource (rooms, settings, finance,
  availability, …), so a features-only edit blows away and refetches every open
  tab plus the availability caches. Narrow these to the specific sub-key
  (`properties.features(id)` etc.). Correctness-safe today, but it is what
  hides the *missing*-invalidation class above — the calendar happens to
  refetch here for the wrong reason.

## Acceptance

- Test (component or hook): after `modifyBookingDates` / confirm / cancel, the
  property availability calendar query for that property is invalidated (assert
  via a spy on `invalidateQueries` or a refetch on the calendar key).
- Test: after convert/send/cancel touching a contact-linked entity, the
  relevant `contacts.detail(id)` subtree is invalidated.
- `grep` shows booking/quotation/enquiry mutations route through the shared
  dependents helper(s), not bespoke per-hook key lists.
- `useUpdatePropertyFeatures` invalidates `properties.features`, not the whole
  `properties.detail` subtree.
- Quality gate green (vitest + eslint + prettier + tsc).

## Dependencies

- Overlaps [REFACTOR-001](refactor-001-frontend-boilerplate-consolidation.md)
  (the optimistic-update / shared-hook cleanup) — the invalidation map is the
  data-fetching half of the same "stop copy-pasting cache logic" theme; land
  the map here since it fixes live bugs, fold the boilerplate there.
- No backend change.
