# GAP-061 — Security-deposit release/refund automation is unbuilt; holds sit open indefinitely

- **Severity:** 🟠 Gap (designed surface — fields, indexes, and service methods exist; the automation that drives them does not)
- **Source:** the 2026-07-02 backend complexity audit (unfinished money-lifecycle surface)
- **Files:** `payments/tasks.py:401` (`process_sd_refunds` — empty `TODO` body),
  `villacollective/settings/base.py:283–285` (deliberately **not** in
  `CELERY_BEAT_SCHEDULE`),
  `payments/models/security_deposit.py:58,60` (`hold_expires_at`,
  `release_scheduled_for`) + `:98–99` (indexes on both),
  `payments/signals.py:217–218` (`_close_money_on_booking_closed` logs
  `payment.sd_review_required` and leaves the hold in place),
  `payments/services/security_deposit.py` (`release`/`expire` — only ever
  called from `views/track.py`, i.e. a manual operator click)

## Problem

The security-deposit model advertises an automated release/expiry SLA the
code does not honour:

- Every SD stores `release_scheduled_for` (PRE_AUTH_HOLD / BT past release
  date) and `hold_expires_at` (void expired holds) at creation, and both are
  **indexed** (`security_deposit.py:98–99`) — clearly intended to be scanned.
- The only thing meant to scan them, `process_sd_refunds`
  (`tasks.py:401`), is an **empty `TODO` body**. It is correctly kept out of
  `CELERY_BEAT_SCHEDULE` (`base.py:283`) so it can't error on every tick — but
  that means nothing scans the fields at all.
- `SecurityDepositService.release()` / `.expire()` are only reachable from
  `views/track.py` (a manual operator action). The booking-close path
  (`_close_money_on_booking_closed`, `signals.py:217`) explicitly does **not**
  auto-release a held SD — it logs `sd_review_required` and leaves it open.

So every pre-auth hold and BT-refundable deposit stays open until a human
remembers to click release.

## Why it bites

Real guest money: pre-auths expire silently at the gateway (a mismatch vs
VC's own SD state), or BT refunds owed to guests are never issued, until an
operator notices. The liability scales linearly with booking volume, and the
data model + indexes make it *look* like a working, SLA-backed feature. This
is a compliance/CX risk, not just tidiness.

## Proposed fix

Implement `process_sd_refunds` as the scan-and-dispatch loop the docstring
already fixes: two branches —

1. `PRE_AUTH_HOLD` / `BT_REFUNDABLE` where `release_scheduled_for <= today`
   → `SecurityDepositService.release(...)`.
2. Holds where `hold_expires_at <= now` → `SecurityDepositService.expire(...)`.

Then add it to `CELERY_BEAT_SCHEDULE` (removing the "must not fire" caveat at
`base.py:283`). Thread an **idempotency key** into the internal
`RefundService.request(...)` call the release path opens (e.g.
`f"sd-release-{sd.pk}"`) so a re-fired sweep can't double-open a refund —
refunds have no one-active constraint (see the audit's payments findings).

Alternative if automation is genuinely still deferred: delete the fields and
indexes so the schema stops advertising an SLA the code doesn't keep, and say
so here — but the fields exist and are indexed, so implementing is the
expected close-out.

## Acceptance

- `process_sd_refunds` releases SDs past `release_scheduled_for` and voids
  holds past `hold_expires_at`; it is registered in `CELERY_BEAT_SCHEDULE`.
- Test: an SD with `release_scheduled_for` in the past is released by one task
  run; a running-twice test proves idempotency (no second refund opened).
- The `base.py` "must not be scheduled" comment is removed once the body is
  real.

## Dependencies

Depends on the SD state machine and `RefundService` idempotency (FG-005
lineage). Related: the audit's payments findings (SD transition table /
`RefundService.from_cancellation` unwired / rounding) may become sibling
tickets. Shares the booking-close signal path with SMELL-020.
