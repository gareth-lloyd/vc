> **✅ RESOLVED (2026-06-15)** — Problem: Audit signals skipped bulk writes and merge FK rewrites went unaudited. Fix: record_merge now folds the FK-rewrite counts into the deletion audit row. Commit: 7bc346a.
>
> _Original ticket preserved below for context._

# FG-016 — Audit signals skip bulk writes; merge FK rewrites unaudited (spec claims otherwise)

- **Severity:** 🟠 Footgun
- **Source:** the 2026-06-11 audit-logging review
- **Files:** `core/audit.py` (`_pre_save_handler` / `_post_delete_handler`),
  `accounts/models/contact.py:99` (`merge`),
  `reservations/models/guest.py:166` (`merge`),
  `00-conventions.md` (AuditLog section)

## Problem

The audit trail rides `pre_save` / `post_delete` signals, so
`queryset.update()`, `bulk_create()` and `bulk_update()` bypass it
silently. Nothing enforces or even documents this. (Same failure family as
FG-011's adjustment recompute.)

Concrete instance today — **spec and code disagree**:
`00-conventions.md` says `Contact.merge(target)` documents the merge with
"one `AuditLog` row per FK rewrite". The implementation rewrites each
reverse relation via `related_model._default_manager.filter(...).update(...)`
— no signals fire, so none of those rows exist. Only the final deletion row
is written. The rewrites touch *tracked* fields on tracked models (e.g.
`Booking.agent_id` is in Booking's tracked field list), so the audit trail
of "this booking's agent changed" is simply missing for merges.

## Proposed fix

1. **Resolve the spec drift** — pick one:
   - (cheap, recommended) stamp a summary into the deletion row instead:
     `field_diffs["__merged_into__"] = target_pk` plus per-relation rewrite
     counts (`{"reservations.Booking.agent": 3, ...}`), collected during the
     `_meta.related_objects` walk; amend `00-conventions.md` to match; or
   - make the spec true: loop `.save()` per rewritten row (O(n) saves —
     probably not worth it at current volumes).
2. **Document the blind spot** as a convention in `django_res/CLAUDE.md`
   (§AuditLog registration): bulk writes to tracked models must either go
   through `.save()` loops or write an explicit audit row.
3. If the blind spot ever matters wholesale (more bulk paths on tracked
   models), the structural fix is trigger-based capture
   (`django-pghistory`) rather than more signal plumbing — note as the
   escape hatch, don't build now.

## Acceptance

- `00-conventions.md` and the merge implementation agree.
- Test: merging a contact with bookings leaves a deletion row carrying
  `__merged_into__` + rewrite counts.
- CLAUDE.md convention paragraph exists.

## Resolution

✅ Took the cheap, recommended path (option 1 — summary on the deletion row).

- New `core.audit.record_merge(obj, target_pk, rewrites)`: atomic, row-locking
  helper that folds `__merged_into__` (destination pk) and `__rewrites__`
  (`{"<model>.<field>": count}`) into the `__deleted__` AuditLog row that
  `post_delete` already wrote. No O(n) per-row saves; no new bulk-signal
  framework (only two merge sites exist).
- `Contact.merge` and `Guest.merge` now capture the `.update()` row count per
  reverse relation (zero-count relations omitted) and call `record_merge`
  *before* `scrub_pii`, so the augmented row is PII-scrubbed too (BUG-012
  ordering preserved).
- Spec drift resolved: `00-conventions.md` row 47 corrected (the old "one
  AuditLog row per rewrite" claim was never true — `.update()` fires no
  signals).
- Blind-spot convention added to `django_res/CLAUDE.md` §AuditLog: bulk writes
  to tracked models bypass the signals; use `.save()` loops or an explicit
  audit row; `django-pghistory` is the escape hatch if bulk paths proliferate
  (not built now).
- Tests: `test_merge_deletion_row_records_merged_into_and_rewrite_counts` in
  both `accounts/tests/test_contact.py` and `reservations/tests/test_guest.py`.

FG-017 (BookingHold/Property tier) and SMELL-016 (threadlocal actor) remain
for follow-up tickets.

## Dependencies

- Related: FG-011 (same signals-skip-bulk family), BUG-012 (merge deletion
  row is also where PII scrubbing applies — coordinate the two changes to
  the deletion-row shape).
