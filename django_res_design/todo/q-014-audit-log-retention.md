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

## Follow-up once answered

- Cleanup Celery beat task if retention is finite.
- Frontend audit log screen (or omit if admin-only).
- Document in `00-conventions.md`.
