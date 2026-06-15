> **✅ RESOLVED (2026-06-15)** — Problem: Quotation.expire() only handled the SENT to EXPIRED transition. Fix: Extended expire() to take DRAFT/SENT to EXPIRED.
>
> _Original ticket preserved below for context._

# SMELL-002 — `Quotation.expire()` only handles `SENT → EXPIRED`

- **Severity:** 🟡 Smell
- **Source:** the 2026-05-26 data-model deep audit §S2
- **Files:** `reservations/models/quotation.py:119–122`

## Problem

`DRAFT` quotations that age past `expires_at` can't expire — only
`cancel()` works on them. The Celery beat that expires quotations would
have to know to also clean up DRAFTs, but the model doesn't let it.
Minor hole in the state machine.

## Proposed fix

Extend `Quotation._transition` (or whatever the state machine entry is)
so `DRAFT → EXPIRED` is allowed when triggered by the expiry sweeper.
Distinguish the user-cancel path (`DRAFT → CANCELLED`) from the
time-based expiry path so the audit trail keeps the reason clear.

## Resolution

✅ `Quotation.expire()` now accepts `DRAFT` as well as `SENT` (both live states
age out at `expires_at`). The user-cancel path stays `DRAFT/SENT → CANCELLED` via
`cancel()`, so the time-based `EXPIRED` status remains distinct from an operator
cancellation in the audit trail. Tests: `test_expire_from_draft` (new),
`test_expire_from_terminal_raises` (new), `test_expire_from_sent` (existing).

Note: no quotation expiry Celery task exists yet (only `expire_holds` for
`BookingHold`); when one is added it should sweep both DRAFT and SENT rows past
`expires_at`. The model now permits that.

## Dependencies

None.
