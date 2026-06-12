# SMELL-006 — `Booking.terms_accepted_at` required but has no default

- **Severity:** 🟡 Smell
- **Source:** the 2026-05-26 data-model deep audit §S6
- **Files:** `reservations/models/booking.py:107`

## Problem

Required, non-null `DateTimeField` with no `auto_now_add`, no
service-level guarantee. Factory code and the API must remember to set
it. When forgotten, the error is a generic
`IntegrityError: NOT NULL constraint failed`, not a
domain-meaningful "terms not accepted".

## Proposed fix

Either:

1. **Service-level guard.** `BookingService.create_from_quotation_line`
   raises a typed `TermsNotAccepted` error if `terms_accepted_at` is
   missing. The factory either accepts or auto-stamps for test paths.
2. **Auto-stamp from upstream.** When the API view receives a booking
   creation request, require an explicit `terms_accepted=true` flag and
   stamp `terms_accepted_at = timezone.now()` server-side.

Recommendation: option 2 — the API surface should require the explicit
acceptance signal; the column then becomes derived rather than user-supplied.

## Dependencies

None.

## Resolution (2026-06-12)

Implemented option 2. By the time of the fix the service layer
(`BookingService.create_from_quotation_line`) already auto-stamped
`terms_accepted_at = timezone.now()`, so the remaining gap was the
explicit acceptance signal at the API surface:

- `POST /quotations/{id}:convert` now requires `terms_accepted: true` in
  the body; missing/false → 400 with the new typed
  `core.exceptions.TermsNotAccepted` (`code: terms_not_accepted`).
- `terms_accepted_at` stays derived/server-stamped — never user-supplied.
- Frontend `ConvertQuotationDialog` sends `terms_accepted: true`
  (`ConvertQuotationInput` requires it).

Tests: `test_convert_without_terms_accepted_400s`,
`test_convert_stamps_terms_accepted_at_server_side`
(`reservations/tests/test_api_quotations.py`).
