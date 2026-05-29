# FG-007 — `SyncRecord` GenericFK leaves dangling rows on target delete

- **Severity:** 🟠 Footgun
- **Source:** `findings/2026-05-26-data-model-deep-audit.md` §F7
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

## Dependencies

None.
