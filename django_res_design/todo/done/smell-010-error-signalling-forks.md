> ✅ **RESOLVED (2026-06-21)** — branch `smell-010-error-signalling-converge`.
>
> **Problem:** Services signalled "operation refused" three ways — typed
> `DomainError`s (intended), bare `ValueError`/`PermissionError` (re-mapped by
> a per-view `_run_service` catch; any view that forgot it 500'd), and DRF
> `ValidationError` imported straight into the service layer (`quotations.py`,
> and — per the 2026-06-19 critique — newly `charges.py` too), coupling
> business logic to the HTTP framework and skipping the canonical `code`.
>
> **Fix:** Converged on pattern 1 (typed `DomainError`).
> - Added `core.exceptions.DomainValidationError` (code `validation_error`,
>   400, carries `field_errors`) — the service-layer counterpart to DRF's
>   `ValidationError` — and `AuthorizationError` (code `forbidden`, 403).
> - `reservations/services/{charges,quotations}.py`: DRF `ValidationError`
>   raises → `DomainValidationError`; both `rest_framework` imports removed.
> - `payments/services/refund.py`: state guards → `InvalidPaymentState`
>   (409 `invalid_state`), permission guards → `AuthorizationError`
>   (403 `forbidden`), `request()` amount guards → `DomainValidationError`
>   (were uncaught → 500, now 400). The `request_refund_for_booking` latent
>   500s are gone.
> - `payments/views/refund.py`: deleted `_run_service`; the action endpoints
>   call the service directly and the canonical handler maps every rejection.
> - Enforcement: an **import-linter `forbidden` contract** ("services are
>   framework-free — no `rest_framework` in the service layer", scoped to every
>   `<app>/services/**`, `allow_indirect_imports` so the blessed
>   `core.api.permissions → rest_framework` chain is exempt). Run in pre-commit
>   + CI alongside the existing layers contract. (Chosen over the ticket's
>   suggested ruff `TID251` because ruff's `banned-api` is global-only and
>   views/serializers legitimately import DRF exceptions; import-linter is the
>   project's path-scoped import-boundary tool and would have caught the
>   `charges.py` regression.)
> - Tests: canonical `{code}` shape pinned at the API level per migrated error
>   type — charges `validation_error`, refund `invalid_state` + `forbidden`;
>   quotations rejection pins `code`/`status_code` on the raised
>   `DomainValidationError`. Existing service-level `PermissionError`/DRF
>   `ValidationError` expectations updated to the new types.
>
> Acceptance met: no `rest_framework` imports under `*/services/` (contract
> enforces it); refund views carry no `except ValueError`/`PermissionError`
> re-mapping. Detailed original ticket below.

---

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
