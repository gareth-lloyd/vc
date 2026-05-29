# SMELL-006 — `Booking.terms_accepted_at` required but has no default

- **Severity:** 🟡 Smell
- **Source:** `findings/2026-05-26-data-model-deep-audit.md` §S6
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
