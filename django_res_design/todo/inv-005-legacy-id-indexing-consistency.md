# INV-005 — `legacy_id` indexing consistency

- **Status:** ✅ **CLOSED** (2026-05-27 critique) — contract holds.
  ~30 models carry `legacy_id = CharField(max_length=64, null=True,
  blank=True, db_index=True)` with consistent shape. All inspected
  loaders in `data_migration/loaders/*` key dedupes on `legacy_id`
  (composite for `PropertyContactAssignment`). No gaps; no migration
  needed.
- **Severity:** Investigation
- **Source:** `findings/2026-05-26-data-model-deep-audit.md` "What I'd
  want to investigate further" item 5

## Question

The survey claims `legacy_id` is present on every importable model with
`db_index=True`. Verify:

- Is the index actually on every relevant model?
- Are all loaders keying their `update_or_create` on `legacy_id`
  (the documented contract)?

## Suggested probe

```
rg -n "legacy_id = models.CharField" django_res/
rg -n "update_or_create" django_res/data_migration/loaders/
```

Confirm `db_index=True` on every match; confirm every loader uses
`legacy_id` as the dedupe key.

## Outcome

If gaps exist, file a small migration to add the missing index, or open
a bug ticket for the loader that's deviating from the contract. Either
way this is a quiet, high-leverage check before the cutover load.
