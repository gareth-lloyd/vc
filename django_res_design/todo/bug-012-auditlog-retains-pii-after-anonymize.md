# BUG-012 — AuditLog retains cleartext PII after `anonymize()` / `merge()`

- **Severity:** 🔴 Bug (GDPR Art. 17 erasure defect)
- **Source:** the 2026-06-11 audit-logging review
- **Files:** `reservations/models/guest.py:131` (`anonymize`),
  `reservations/models/guest.py:166` / `accounts/models/contact.py:99`
  (`merge`), `core/audit.py` (`_pre_save_handler`, `_post_delete_handler`),
  `reservations/apps.py:26–42`, `accounts/apps.py:15–27`

## Problem

Guest and Contact PII fields (`first_name`, `last_name`, `email`, `phone`,
addresses, `notes`) are audit-tracked **without** the `sensitive=` flag —
deliberately, since redacting them at write time would gut day-to-day audit
value. But that means the erasure flows leak:

1. **Historical rows**: every prior edit to a guest/contact left cleartext
   PII in `AuditLog.field_diffs`. `anonymize()` overwrites the model row
   and touches nothing in `AuditLog`.
2. **The anonymize save itself** writes a *fresh* audit row whose diffs are
   `[old_PII, sentinel]` — faithfully preserving the exact values being
   erased, stamped at the moment of the erasure request.
3. **`merge()` hard-deletes** fire `_post_delete_handler`, which records
   *all* tracked field values (`[old_PII, None]`) in the deletion row.

So a GDPR erasure request currently leaves the subject's PII fully
recoverable from the audit table, forever (no retention policy exists —
Q-014).

## Proposed fix

A `core.audit.scrub_pii(obj, fields)` helper that rewrites the named keys'
values to `core.audit.REDACTED` across all `AuditLog` rows for
`(content_type, object_id)` — both sides of each diff pair. Call it inside
`Guest.anonymize()` and at the end of `Guest.merge()` / `Contact.merge()`
(after the delete, scrubbing by the now-dead pk), in the same
`transaction.atomic`.

Notes:

- This is the standard GDPR carve-out from "append-only": row identity,
  actor, timestamps, and *which fields changed* survive; only the values go.
- Do **not** instead mark the PII fields `sensitive=` — that destroys the
  audit trail's usefulness for live records.
- The anonymize save ordering matters: scrub *after* the save so the
  freshly written `[old, sentinel]` row is caught too.

## Acceptance

- Test: edit a guest's email, `anonymize()`, assert no `AuditLog` row for
  that guest contains the old email (including the anonymize-save row).
- Test: `merge()` a contact, assert the deletion row's PII values are
  redacted but `__deleted__`, actor, and timestamps survive.
- Convention note in `00-conventions.md` §AuditLog: erasure flows must call
  `scrub_pii`.

## Dependencies

- Informs **Q-014** (with scrubbing in place, keep-forever retention
  becomes defensible) and **Q-010** (guest data retention).
