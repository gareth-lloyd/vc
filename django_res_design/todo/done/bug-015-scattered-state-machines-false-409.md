# BUG-015 — State-machine transitions hand-rolled four ways; SD's bare `ValueError` maps unrelated errors to false 409s, and some lifecycles are unguarded

> **✅ RESOLVED (2026-09-17, local `main` unpushed)** — shipped on `feat/bug-015`
> in 10 units (20f1cee2 primitive, facda6c4 SD typed errors, 55ba58dc
> Payment/Refund, 768716a3 Booking, e7921545 Enquiry, a165447f Quotation,
> e4ad2723 DamageClaim/Property, eb780e4c + d8680ec8 BookingHold, docs).
> **Fix:** `core/transitions.py` (`transition` / `assert_allowed` /
> `can_transition`) is the one lock → table guard → `save(update_fields)` →
> event-writer primitive (event row where the aggregate has an event table),
> and all nine status machines route through it against a single
> `<ENTITY>_ALLOWED_TRANSITIONS` table in their app's `enums.py` — the one
> bulk exception is `HoldService.release_for_*` (`queryset.update()` on LIVE
> holds, no audit row, as before). It is **Q-024-neutral** — no signal moved. SD refusals are typed
> (`InvalidTransition` 409, `InvalidSecurityDepositKind`,
> `DomainValidationError` 400) and `track.py::_service_call` now remaps only
> `IntegrityError`, so an unrelated `ValueError` is a real error again, not a
> false 409. Callers stop re-listing allowed-from (`can_transition` in
> quotation accept/transmission and SD claim → DamageClaim settle; the
> quotation `:convert` view no longer re-derives it); rules deliberately
> narrower than a table (the SD booking-terminal signal, gateway
> capture/void, quotation editability) keep an explicit, commented tuple.
> `BookingHold` gained a `status` column (LIVE / RELEASED / EXPIRED,
> migrations 0014 backfill + 0015 constraints) with a CHECK tying
> `released_at IS NULL` ⇔ LIVE, so a released-and-live row is
> unrepresentable. Expiry is per row and re-checked under the lock; readers
> share `BookingHold.live_q()`; closed or lapsed holds are read-only; an
> explicit past `expires_at` is a 400; new `HoldService.extend`.
> **Stale in this ticket:** `DamageClaim` was already guarded
> (`DamageClaimService._transition`) — only its enum docstring said
> otherwise; it now shares the primitive. **Deferred:** OwnerBlock
> cancel/contest; `Enquiry.set_lead_status`'s bare `ValueError` (not a
> transition, view pre-validates); surfacing `InvalidTransition.allowed` in
> the API body. **Deploy note:** between `migrate` and the instance swap, old
> code's bulk hold release violates the new CHECK (accepted; no live traffic).
>
> _Original ticket preserved below for context._

- **Severity:** 🔴 Bug
- **Source:** the 2026-07-02 backend complexity audit (transition enforcement scattered)
- **Files:** `payments/models/security_deposit.py:165–327` (bare `ValueError`
  guards), `payments/views/track.py:86–99` (`_service_call` blanket
  `ValueError → 409`), `reservations/models/booking.py:247–315`
  (`Booking._transition`), `reservations/models/enquiry.py:224–262`
  (`Enquiry._transition`), `reservations/models/quotation.py:109–217`
  (`_assert_from` inlined per method), `payments/enums.py`
  (`PAYMENT_ALLOWED_TRANSITIONS` / `REFUND_ALLOWED_TRANSITIONS`),
  `reservations/apps.py:197–205` (`BookingHold` has no status column),
  `reservations/enums.py:297–306` (`DamageClaimStatus` unenforced pre-wf8)

## Problem

There are eight status enums but no shared transition primitive — "lock,
guard, mutate, write event" is reimplemented four different ways, and the
divergence has produced a live defect:

- **False 409s (the concrete bug).** Payment and Refund validate against a
  central `dict` (`PAYMENT_ALLOWED_TRANSITIONS`, `REFUND_ALLOWED_TRANSITIONS`)
  and raise a typed error. `SecurityDeposit` instead hard-codes
  `if self.status != X: raise ValueError(...)` in each of seven
  `transition_to_*` methods (`security_deposit.py:169,182,211,213,236,240,272`
  …). Because those are **bare `ValueError`s**, `track.py:_service_call`
  (`track.py:86–99`) catches `ValueError` wholesale and remaps it to HTTP 409
  — so *any* unrelated `ValueError` raised anywhere in that call path (a bad
  parse, a downstream library) surfaces to the operator as a spurious
  "409 Conflict — void or settle the existing row first," masking the real
  error. (SMELL-010 converged the rest of the codebase onto typed
  `DomainError`; SD is the straggler.)

- **Unguarded lifecycles.** `BookingHold` has **no status column** — its
  lifecycle is implied by `released_at`/`expires_at` (`apps.py:197–205`), so
  there is no transition to enforce and invalid combinations are representable.
  `DamageClaimStatus` ships as an enum whose enforced machine "lands with
  workflow 8" (`enums.py:297–306`) — an ungated field until then.

- **Duplicated allowed-from sets.** The eligible-state sets are duplicated
  between models and their callers (e.g. the quotation view re-derives
  SENT/ACCEPTED gating, and `Quotation.accept` re-lists eligible enquiry
  states), so a state added in one place silently diverges from its copy.

## Why it's a bug (not just a smell)

The `ValueError → 409` remap is wrong **today**: it reports the wrong HTTP
status and hides genuine failures on every SD action path. The unguarded
`BookingHold`/`DamageClaim` states permit invalid combinations to be persisted
now. Both are "service allows/represents invalid state today," which is the
bug bucket, not the smell bucket.

## Proposed fix

- Give `SecurityDeposit` a table (`SD_ALLOWED_TRANSITIONS` in
  `payments/enums.py`) and a single `_transition` that raises the typed
  `DomainError`/`InvalidTransition` (matching Payment/Refund); drop the bare
  `ValueError`s so `track.py` no longer needs the blanket remap (narrow the
  `except` to the typed error).
- Extract **one** transition primitive (guard table + event writer + optional
  signal) and express `Booking`/`Enquiry`/`Quotation`/SD machines as data, so
  allowed-from lives in exactly one place per entity and callers stop
  re-listing it.
- Give `BookingHold` an explicit status (or document + constrain the
  `released_at`/`expires_at` invariant with a `CheckConstraint`).

## Acceptance

- Test: an SD action that hits an unrelated `ValueError` no longer returns 409;
  an actual illegal SD transition returns 409 via the typed error.
- Every state machine routes through one primitive; `grep` finds a single
  allowed-transition table per entity, and no view re-derives allowed-from.
- `BookingHold` cannot represent a released-and-live combination (constraint
  or status).

## Dependencies

Shape depends on Q-024 (does the transition primitive fire signals or call an
orchestration service?). Sibling to SMELL-010 (typed `DomainError`
convergence), BUG-011 (SD bare `ValueError` → 500, the same class one layer
down). Touches GAP-054 (DamageClaim wf8 machine).
