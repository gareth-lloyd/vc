# SMELL-002 — `Quotation.expire()` only handles `SENT → EXPIRED`

- **Severity:** 🟡 Smell
- **Source:** `findings/2026-05-26-data-model-deep-audit.md` §S2
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

## Dependencies

None.
