# Q-014 — Audit log retention window

- **Severity:** Question
- **Source:** `product-design/06-verification.md` open question 14
- **Blocks:** `core.audit` cleanup task, operator UI surface

## Question

Confirm:

- Retention window — **forever** / **7 years** / **per regulatory
  requirement** (e.g. financial-record rules in the operating
  jurisdictions)?
- Should the operator UI expose the audit log, or is it admin-only?

Note that any PII-tracked entries (`sensitive=` in `core.audit.track`)
have stricter constraints under GDPR — retention may have to vary by
field, not just by entity.

## Recommendation (2026-06-11 audit-logging review)

**Keep-forever + PII scrubbing** (BUG-012) is the defensible answer: with
`scrub_pii` called from the erasure flows, the GDPR axis is handled at the
*subject* level rather than by a blanket time window, and the table stays
cheap (diff-only rows, no blobs). A finite window can be added later
without schema change. The second question (operator vs admin-only
exposure) now blocks GAP-021 (per-entity History tab).

## Follow-up once answered

- Cleanup Celery beat task if retention is finite.
- Frontend audit log screen (or omit if admin-only) — see GAP-021.
- Document in `00-conventions.md`.

## Dependencies

- **BUG-012** (AuditLog retains PII after anonymize/merge) — the scrub is
  a precondition for the keep-forever recommendation.
- Blocks **GAP-021** (exposure half only).
