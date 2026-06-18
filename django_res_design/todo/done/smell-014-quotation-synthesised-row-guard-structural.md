> **✅ RESOLVED (2026-06-18)** — Problem: the `booking-` synthetic-row
> exclusion was opt-in, with one hand-rolled `.startswith("booking-")` re-filter
> in `GuestEnquirySerializer`. Verified (as the ticket suspected) that this was
> the only hand-rolled copy — every viewset already routes through `.real()`.
> Fix: replaced the literal with `.real()` (reuse the already-`.real()`'d
> prefetch cache when primed, hit the DB via `.real()` on the unprimed
> fallback), so no synthetic predicate lives outside `real()` and the loader.
> Added pinning tests for the `/quotations` list and the unprimed serializer
> path. Commit: bcd9013.
>
> _Original ticket preserved below for context._

# SMELL-014 — Synthesised `booking-` quotation rows: make the exclusion structural

- **Severity:** 🟡 Smell
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `reservations/models/quotation.py:25–39`,
  `reservations/serializers/guest.py:155–156`, `django_res/CLAUDE.md`
  ("Synthesised rows must not leak into public APIs")

## Problem

Legacy bookings carry synthesised Quotation/QuotationLine rows
(`legacy_id` prefixed `booking-`) that must never surface in operator or
guest APIs. A shared opt-in queryset exists
(`QuotationQuerySet.real()` / `QuotationLineQuerySet.real()`,
quotation.py:25–39), but the guard is still convention-enforced: every new
viewset/serializer must *remember* to call `.real()`, and at least one
surface hand-rolls the predicate instead:

```python
# reservations/serializers/guest.py:156
return [q for q in obj.quotations.all() if not (q.legacy_id or "").startswith("booking-")]
```

> **Verify first:** the review plan described the exclusion as fully
> convention-only; `real()` already centralises the predicate, so the
> remaining gap is narrower — it's opt-in rather than default, plus the
> duplicated Python re-filter above. Confirm no other hand-rolled copies
> exist before scoping.

## Proposed fix

Make leakage structurally impossible: either a default manager that
excludes synthetic rows (with an explicit `include_synthetic()` /
`objects_all` escape hatch for loaders and the PROTECT-chain code that
legitimately needs them), or — if a default manager is judged too sneaky
for FK traversal semantics — keep `real()` opt-in but (a) replace the
`guest.py:156` re-filter with the queryset method and (b) add a pinning
test that walks every Quotation-surfacing endpoint and asserts no
`booking-` row leaks.

## Acceptance

- The hand-rolled re-filter in `reservations/serializers/guest.py` is gone.
- A regression test fails if a Quotation/QuotationLine API surface returns
  a `legacy_id__startswith="booking-"` row.

## Dependencies

None.
