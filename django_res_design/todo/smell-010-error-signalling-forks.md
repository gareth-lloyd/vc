# SMELL-010 — Three coexisting error-signalling patterns in the service layer

- **Severity:** 🟡 Smell
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `core/exceptions.py` + `core/api/exception_handler.py:53`,
  `payments/services/refund.py:153,175,202,234`,
  `reservations/services/quotations.py:10,155,178`

## Problem

Services signal "this operation is refused" three different ways:

1. **Typed domain errors** — `core.exceptions.DomainError` subclasses
   (`InvalidTransition`, `InvalidPaymentState`, …) mapped to 409 + stable
   `code` by `canonical_exception_handler`. The intended pattern.
2. **Bare `ValueError`/`PermissionError`** — `refund.py` state guards, with
   per-view catches re-mapping them (`payments/views/refund.py:32,41`);
   any view that forgets the catch 500s (see BUG-011 for the SD case).
3. **DRF `ValidationError` imported into the service layer**:

   ```python
   from rest_framework.exceptions import ValidationError   # quotations.py:10
   raise ValidationError("Cannot quote a lost or converted enquiry.")  # :155
   ```

   This couples business logic to the HTTP framework and skips the
   canonical `{code, detail, field_errors}` shape's `code`.

Every new service re-picks a pattern; every new view has to know which
catches it needs.

## Proposed fix

Converge on pattern 1: typed `DomainError` subclasses raised by services,
no per-view catches, the canonical handler does the mapping. Migrate
`refund.py`'s `ValueError`s (and the views' now-dead catches) and
`quotations.py`'s DRF import. Consider a ruff `TID251` ban on
`rest_framework.exceptions` inside `*/services/**` to keep it converged.

## Acceptance

- No `rest_framework` imports under `*/services/`; refund/quotation views
  carry no `except ValueError` re-mapping.
- API tests assert the canonical error shape (`code` present) for one
  rejected transition per migrated service.

## Dependencies

BUG-011 implements the security-deposit slice. Related: SMELL-008 (same
files, converge in the same passes).
