> **✅ RESOLVED (2026-06-15)** — Problem: SyncRecord's GenericFK left dangling rows when the target was deleted. Fix: Added post_delete cleanup via a registry to remove orphaned SyncRecord rows.
>
> _Original ticket preserved below for context._

# FG-007 — `SyncRecord` GenericFK leaves dangling rows on target delete

- **Severity:** 🟠 Footgun
- **Source:** the 2026-05-26 data-model deep audit §F7
- **Files:** `integrations/models/sync_record.py`,
  `integrations/apps.py` (add signal wiring),
  `integrations/signals.py` (already exists)

## Problem

`SyncRecord` uses `ContentType + object_id` (GenericFK). `Contact.merge()`
hard-deletes the absorbed contact; `Quotation` can be hard-deleted. No
signal removes `SyncRecord` rows pointing at deleted targets — queries
that resolve `.target` get silent-empty results.

## Proposed fix

Pick one:

1. **`pre_delete` signal** in `integrations.apps.ready()` for each
   target model: delete (or mark `is_orphaned=True`) the `SyncRecord`
   rows whose `(content_type, object_id)` matches the row being deleted.
   Simple, covers all callers.
2. **Typed sync tables** — one per synced model with a real FK. Strongest
   integrity but a bigger schema change; tracking ticket only if
   GenericFK pain becomes recurrent.

Recommendation: option 1 for now.

## Acceptance

- Deleting a `Contact` / `Quotation` removes (or orphans) the
  corresponding `SyncRecord` rows in the same transaction.
- Test covering Contact merge and direct Quotation delete.
- `_meta.related_objects` walk in `Contact.merge` is updated if needed
  to handle the SyncRecord cleanup.

## Resolution

✅ Chose option 1 (`post_delete` cleanup), wired into the existing
`register_sync_target` registry rather than per-model in each app's `ready()`.
`integrations/signals.py` now connects a `_post_delete_handler` (dispatch_uid
`…:del`) alongside the save handlers; `unregister_sync_target` disconnects it.
The handler deletes every `SyncRecord` whose `(content_type, object_id)` matches
the deleted target, in the same transaction. Because it keys off the registry,
it only fires for registered sync targets (none in production yet — hence the
"no live targets" note), and any future-registered model is covered for free,
including `Contact.merge`'s hard-delete of the absorbed row and direct
`Quotation` deletes.

Tests (`integrations/tests/test_signals.py`):
`test_delete_target_removes_its_sync_records` and
`test_unregister_sync_target_disconnects_delete_handler`.

## Dependencies

None.
