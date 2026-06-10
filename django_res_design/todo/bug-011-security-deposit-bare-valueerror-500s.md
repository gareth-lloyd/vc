# BUG-011 — SecurityDeposit service raises bare `ValueError` → 500s; zero log events

- **Severity:** 🔴 Bug
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `payments/services/security_deposit.py:111,153`,
  `payments/views/track.py:164–211`, `core/api/exception_handler.py:53`

## Problem

The SD kind guards raise bare `ValueError`:

```python
raise ValueError(f"SD {sd.reference}: :hold only valid for PRE_AUTH_HOLD kind")   # :111
raise ValueError(f"SD {sd.reference}: :mark-paid only valid for BT_REFUNDABLE kind")  # :153
```

The track views (`security_track_action`, `security_payment_action`) call
`SecurityDepositService.mark_paid/hold/release/claim` with no `except` —
and `canonical_exception_handler` only maps `DomainError` subclasses
(`InvalidPaymentState`, `NoActiveSecurityDeposit`, …) to 4xx. A wrong-kind
SD transition therefore returns a 500 to the operator UI.

Compounding it: `security_deposit.py` has **zero** structured log events —
the entire SD money state machine (pre-auth, capture, release, claim) is
invisible in logs, unlike the sibling `refund.py`.

## Proposed fix

- Replace the bare `ValueError`s with typed domain errors handled by the
  canonical exception handler — `core.exceptions.InvalidTransition`, or a
  new `InvalidSecurityDepositKind(DomainError)` where the kind (not the
  status) is what's wrong. Audit the rest of the file for the same pattern.
- Add `log_operation` / domain events to the SD transitions per the
  structured-logging convention (money paths earn observability).

## Acceptance

- API test: posting `:mark-paid` against a `PRE_AUTH_HOLD` SD (and `:hold`
  against a `BT_REFUNDABLE` SD) returns 409 with a stable `code`, not 500.
- One money-path test asserts the new events via `capture_logs()` (mirror
  `test_refund_service_emits_structured_events`).

## Dependencies

Implements the SD slice of SMELL-010 (error-signalling convergence).
