# GAP-071 — No way to create a security deposit; auto-creation is the only path

- **Severity:** 🟠 Gap (the `SecurityDeposit` entity, state machine, and read/transition
  API all exist; the only *creation* path is automatic, so a booking that missed it can
  never get one)
- **Source:** 2026-07-03 investigation off the `/bookings/383/payments` empty-state bug
  (booking VC383, checked-out, has no SD — the empty state is a dead end). Fix for the
  empty-state crash landed as `c9e5fac` (204 instead of empty 200); this ticket is the
  product gap that fix exposed.
- **Files:**
  - `payments/services/security_deposit.py` — `create_for_booking` (sole creator;
    idempotent + gated on `effective("security_deposit_required")` and `amount > 0`;
    only caller is the scheduler)
  - `payments/services/payment_scheduler.py:152` — the one production caller
  - `payments/signals.py:49–84` — `_schedule_payments_on_booking_confirmed`, fires only
    on booking → `AWAITING_DEPOSIT` (the single creation trigger)
  - `payments/urls.py` (security routes) + `payments/views/track.py`
    (`security_detail` read-only; `_get_active_sd` raises `NoActiveSecurityDeposit` for
    every action when none exists) — **no POST route creates an SD**
  - `frontend/src/features/bookings/components/SecurityDepositPanel.tsx:67–71` — empty
    state has no `action`; `hooks.ts` / `api.ts` expose only fetch / release / claim

## Problem

A `SecurityDeposit` can only be born automatically, when a booking transitions to
`AWAITING_DEPOSIT` (confirmation) **and** the property finance policy has
`security_deposit_required` truthy **and** the sized amount is `> 0`. There is no
operator-facing way — UI or API — to create one otherwise:

- The frontend empty state ("No security deposit") is purely informational — no button,
  no create mutation anywhere in `features/bookings/`.
- The backend has **no create endpoint at all**. Every SD action endpoint
  (`:release`, `:claim`, `:hold`, `:mark-paid`) first calls `_get_active_sd()` and errors
  with `NoActiveSecurityDeposit` if none exists.

So any booking that didn't auto-create an SD at confirmation is stuck without one.

## Why it bites

Real remediation scenarios have no path:

- A property onboarded/confirmed a booking **before** its SD policy was set, then later
  needs a deposit on that live booking.
- The policy was misconfigured (required = false, or amount = 0) at confirmation time.
- An operator wants an **ad-hoc** SD for a one-off high-risk guest the policy doesn't cover.

Today the only recourse is a Django shell. This is an operations dead-end, not just a
missing nicety.

## Proposed fix

**Backend**
- Add `SecurityDepositService.create_manual(booking, *, amount, currency, kind, actor,
  idempotency_key=None)` (or a flag on `create_for_booking`) that creates an SD
  **independent of the `security_deposit_required` policy gate**, while preserving the
  existing one-active-SD-per-booking invariant and `actor`-based audit (see the service's
  existing `actor` / `idempotency_key` conventions).
- Add a POST endpoint — `POST /bookings/{id}/security/deposit` (or colon-verb
  `security:create`) — wired to it, gated `IsAccountsWriter` (writes need the accounts
  role; reads stay all-staff). Validate `amount > 0`, a real `currency`, and
  `kind ∈ {pre_auth_hold, bt_refundable}`; derive the initial status from `kind` exactly
  as the auto path does. Return the created row via `SecurityDepositSerializer`.

**Frontend**
- Add `useCreateSecurityDeposit` hook + `api.ts` fn; give the `SecurityDepositPanel`
  empty state an "Add security deposit" `action` opening a small dialog (amount /
  currency / kind), accounts-role gated (disabled-with-tooltip per the role-gating
  convention, not hidden). Prefill amount from the property policy when present.
  Invalidate the `["bookings","detail",id,"security-deposit"]` key on success.

### Open product decisions (surface before building)

1. **Terminal bookings** — allow manual creation on checked-out/cancelled bookings?
   (BT-refundable that still needs settling: plausibly yes; a pre-auth hold on a departed
   guest: no.) Booking 383 is checked-out, so this is the motivating case.
2. **Amount source** — prefill from policy vs free entry; may an operator override the
   policy amount?
3. **Existing terminal SD** — block creation only when an *active* SD exists (one-active
   invariant), or also when a terminal one does?
4. **Selectable kinds** — expose both `pre_auth_hold` and `bt_refundable`, or restrict?

## Acceptance

- A new service method creates an SD regardless of `security_deposit_required`, keeps the
  one-active-SD invariant, audits `actor`, and is idempotent on repeat calls.
- POST endpoint: 201/200 with the serialized SD on success; 4xx on bad amount/kind/
  currency; 409 when an active SD already exists.
- FE empty state offers an accounts-gated "Add security deposit" action that creates and
  renders the new SD; tests cover the create path and the non-accounts role-disable.

## Dependencies

Builds on the SD state machine + `SecurityDepositService`. Sibling to **GAP-061**
(release/refund automation) and **GAP-054** (damage-claims remainder). Touches the
property finance policy resolved by **GAP-068 / GAP-070** defaults work. Directly follows
the `c9e5fac` empty-state fix that surfaced the gap.
