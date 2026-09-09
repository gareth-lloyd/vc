# BUG-027 — `enqueue_zoho_push` drops an edit that lands while the push is in flight

> **✅ RESOLVED (2026-09-09, local `main` unpushed)** — shipped on
> `feat/bug-027`: cce9918a. **Fix, two halves.** `ensure_pending_record` now
> ALWAYS re-writes an existing row `PENDING` + `updated_at`, even when it is
> already `PENDING` (status too, not just the touch proposed below, so the
> row stays `PENDING` even if the push's `IN_SYNC` write commits between the
> bump's SELECT and its UPDATE). And `push_sync_record`, when its guarded
> `IN_SYNC` write misses, **re-dispatches itself** if the row is still
> `PENDING` — the bump deliberately deduped against the in-flight task, so
> the superseded task is the only party positioned to re-push; it runs
> after its own POST and the bump has committed, so the next run builds the
> fresh payload. That replaces the "wait one `PUSH_SWEEP_GRACE`" recovery
> proposed below (the ship review showed the touch resets the sweep clock on
> every bump, so a villa under continuous editing would never age into the
> sweep while hot); the sweep stays the backstop for a lost dispatch. A
> miss caused by an `IN_SYNC`/`ERROR`/`DISABLED` stamp does not re-POST.
> Dedupe unchanged: still no second dispatch from the bump, one
> `SyncRecord`. ⚠️ **Candidate follow-ups, not fixed here (pre-existing):**
> the 4xx and builder-error paths in `push_sync_record` write `ERROR` with an
> unguarded save and would overwrite a concurrent bump's `PENDING`; and
> `zoho_backfill` counts a row "left PENDING" after its synchronous push as a
> failure, so a live edit landing mid-backfill-POST reads as a phantom
> failure in the `SyncRun` summary (the edit itself is re-pushed correctly).
> Tests: `test_push_success_yields_to_bump_of_already_pending_row`,
> `test_push_success_superseded_by_non_pending_stamp_does_not_redispatch`,
> and the re-dispatch pinned on `test_push_success_yields_to_concurrent_bump`.

- **Severity:** 🔴 Bug (Zoho silently keeps a stale payload and the
  `SyncRecord` says `IN_SYNC`, so the sweep never repairs it).
- **Source:** GAP-102 unit-4 review (2026-09-08). Pre-existing — shared by
  every bump (Property saves, all `_VILLA_CHILDREN`, the GAP-102 `Extra`
  bump, enquiry notes), not introduced by GAP-102.
- **Files touched (when built):**
  - `django_res/integrations/services/zoho_flow.py` — `ensure_pending_record`
    already-PENDING early return (no `updated_at` touch).
  - `django_res/integrations/tasks.py` — `push_sync_record`'s guarded
    IN_SYNC write `filter(pk=…, updated_at=record.updated_at).update(…)`.
  - `django_res/integrations/tests/test_zoho_flow.py` —
    `test_push_success_yields_to_concurrent_bump` pins the guard for the
    *non*-PENDING bump path only.

## Problem

1. Villa X's record is `PENDING`; the worker has read it and built the
   payload, and is mid-POST.
2. Staff edit (any bump) → `enqueue_zoho_push` → `ensure_pending_record`
   sees the row already `PENDING` and returns early **without touching
   `updated_at`** — no save, no dispatch (correct dedupe intent).
3. The POST returns 2xx. The guarded write compares `updated_at` — unchanged
   — so it matches and stamps `IN_SYNC`.
4. Zoho holds the pre-edit payload; the row is `IN_SYNC`; `push_pending`
   only sweeps `PENDING` rows. The edit reaches Zoho on the next unrelated
   bump — or never.

The guard was designed for the bump-from-non-PENDING case (which does save
and therefore does move `updated_at`) and is pinned by test for that case
only.

## Proposed fix

In the already-PENDING branch still touch the row
(`save(update_fields=["updated_at"])`) so the in-flight worker's guarded
write misses and the row stays `PENDING` for the sweep (`PUSH_SWEEP_GRACE`
is keyed on `updated_at`, so the re-dispatch is delayed by one grace period
— acceptable; the alternative of dispatching a second task races the first).
One line + a test that mirrors `test_push_success_yields_to_concurrent_bump`
but bumps from an already-PENDING row.

## Acceptance

- A bump that lands while the row is already `PENDING` leaves it `PENDING`
  after the in-flight push succeeds. (test)
- The dedupe still holds: no second dispatch, one `SyncRecord`. (existing
  tests)
