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

## Resolution (2026-06-12)

Note on staleness: by the time this landed, the "no `except` → 500" half was
already partially mitigated — FG-012 introduced `_service_call` in
`payments/views/track.py`, which maps service `ValueError`s to a 409
`invalid_state`. The remaining problems (bare `ValueError`s in the service,
no kind-specific stable code, zero log events) were real and are fixed:

- New `core.exceptions.InvalidSecurityDepositKind(DomainError)`
  (`code="invalid_sd_kind"`, 409). The two kind guards in
  `SecurityDepositService.hold` / `mark_paid` raise it; the canonical
  exception handler maps it directly, so operators get a stable
  kind-specific code instead of the generic `invalid_state`. The *status*
  guards on the `SecurityDeposit` model transitions still raise
  `ValueError` (caught by `_service_call`) — converging those is
  SMELL-010's scope.
- The SD money path now logs: `security_deposit.created` (fact event in
  `create_for_booking`) and `log_operation` triples
  `security_deposit.{hold,mark_paid,release,claim,expire}` carrying
  `security_deposit_id` / `booking_id` / `amount` / `currency` (+
  `captured_amount`, `kind`, `method` where relevant). Kind guards sit
  above the `log_operation` block per convention — an expected rejection
  is not a `.failed` traceback.

Tests (written red first): wrong-kind API tests pin 409 +
`code == "invalid_sd_kind"` for `:mark-paid` on PRE_AUTH_HOLD and `:hold`
on BT_REFUNDABLE (`payments/tests/test_api_security_track.py`);
service-level typed-error tests and two `capture_logs()` event tests
mirroring `test_refund_service_emits_structured_events`
(`payments/tests/test_security_deposit.py`).
