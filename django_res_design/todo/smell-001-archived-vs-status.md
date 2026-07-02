# SMELL-001 — `Booking.archived_at` is a second status loosely coupled to `status`

- **Severity:** 🟡 Smell
- **Source:** the 2026-05-26 data-model deep audit §S1
- **Files:** `reservations/models/booking.py:136–139`

## Problem

The constraint `archived_at IS NULL OR status ∈ TERMINAL` makes
`archived_at` a "second status" that the schema only loosely couples to
the real `status` enum. Combined with [BUG-001](done/bug-001-cancelled-status-requires-cancelled-at.md),
it's easy to land an inconsistent pair.

## Proposed fix

Fold the archive bit into the status enum (`ARCHIVED` value, or
combined values like `CANCELLED_ARCHIVED`). One state column, one
constraint. Already raised in survey §6.3.

Alternatively: keep `archived_at` but add a stricter constraint that
`archived_at IS NULL XOR (archived_at IS NOT NULL AND status ∈ TERMINAL)`
plus the inverse from BUG-001.

Defer until either someone touches Booking lifecycle for another reason,
or the next bookings-app refactor.

## Dependencies

[BUG-001](done/bug-001-cancelled-status-requires-cancelled-at.md) should land first.
