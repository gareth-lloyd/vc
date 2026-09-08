# BUG-027 — `enqueue_zoho_push` drops an edit that lands while the push is in flight

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
