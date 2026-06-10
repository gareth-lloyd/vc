# FG-014 — Audit-tracking gaps: SecurityDeposit, Enquiry, Quotation untracked

- **Severity:** 🟠 Footgun
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `payments/apps.py:17–52`, `reservations/apps.py:25–122`,
  `core/tests/test_audit_registry.py`

## Problem

The CLAUDE.md convention says every PII- or money-bearing model must be
registered via `core.audit.track(...)` in `AppConfig.ready()`. Three are
missing:

- `payments.SecurityDeposit` — a full money lifecycle (pre-auth, capture,
  claim, release) while its siblings `Payment` and `Refund` are both
  tracked (`payments/apps.py:17` / `:32`).
- `reservations.Enquiry` — carries direct PII (`first_name`, `last_name`,
  `email`, `phone` at `reservations/models/enquiry.py:47–51`);
  `reservations/apps.py` tracks `Guest` but not the enquiry that holds the
  same fields pre-conversion.
- `reservations.Quotation` header — status / currency / expiry changes have
  no trail (its lines are tracked via `QuotationLine`).

Pricing models (`RatePlan`/`RateCard`/`RateRule`/…) are being registered in
the high-value review branch, so they're out of scope here.

## Proposed fix

Register the three with tight field lists per convention (lifecycle, PII,
money columns; skip `auto_now` timestamps and chatty JSON), and update
`EXPECTED_TRACKED_MODELS` in `core/tests/test_audit_registry.py` in the
same commit.

## Acceptance

- `test_audit_registry.py` pins the three new registrations.
- A status transition on each model lands an `AuditLog` row in an
  integration test (one per model is enough).

## Dependencies

Related: Q-014 (audit-log retention window — more tracked models means the
retention answer matters sooner). Pricing-model registration lands on the
feat/backend-review-fixes branch.
