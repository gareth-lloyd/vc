> **✅ RESOLVED (2026-06-15)** — Problem: SecurityDeposit, Enquiry, and Quotation were not audit-tracked. Fix: Registered SecurityDeposit, Enquiry, and Quotation for audit tracking. Commit: ee7732a.
>
> _Original ticket preserved below for context._

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

## Resolution (✅)

Registered all three via `core.audit.track(...)` in the relevant
`AppConfig.ready()`:

- `payments.SecurityDeposit` (`payments/apps.py`) — status, kind, money
  columns (`amount`, `captured_amount`, `refunded_amount`), `damage_claim_id`,
  the lifecycle stamps (`due_at`, `hold_expires_at`, `release_scheduled_for`,
  `released_at`), `requested_by_id`, `failure_reason`. No PII; the chatty
  `meta` JSON is skipped.
- `reservations.Enquiry` (`reservations/apps.py`) — status + denormalised PII
  (`first_name`, `last_name`, `email`, `phone`) registered `sensitive=`, plus
  routing/assignment FKs (`guest_id`, `property_id`, `agent_id`,
  `assigned_to_id`) and `contact_method` / `request_type`. **PII handling:**
  unlike `Guest`, the Enquiry has *no* `anonymize()`/`scrub_pii` erasure path,
  so its PII is recorded as the `[REDACTED]` sentinel at write time — cleartext
  never reaches the AuditLog, so no retro-scrub wiring is needed. `legacy_id`,
  `inbound_message` free text and `auto_now` stamps are skipped.
- `reservations.Quotation` header (`reservations/apps.py`) — status,
  `expires_at`, `cancel_reason`, `is_unbranded`, and the
  guest/agent/enquiry FKs. No header currency (per-line, GAP-014); money lives
  on `QuotationLine`, already tracked.

`EXPECTED_TRACKED_MODELS` in `core/tests/test_audit_registry.py` updated to pin
the three. Integration tests assert a status transition lands an AuditLog row
for each model, plus an Enquiry test pinning that a PII edit is stored as the
`[REDACTED]` sentinel (not cleartext):
`payments/tests/test_audit_security_deposit.py`,
`reservations/tests/test_audit_enquiry_quotation.py`. No migration required —
audit registration is signal-only. Full `pytest`, `ruff`, `mypy` green.
