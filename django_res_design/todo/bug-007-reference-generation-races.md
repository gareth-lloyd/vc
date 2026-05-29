# BUG-007 — Reference generation races and is bypassed by `bulk_create`

- **Severity:** 🔴 Bug
- **Source:** `findings/2026-05-26-data-model-deep-audit.md` §B7
- **Files:** `core/refs.py:28–40`, `payments/models/payment.py:119–122`
  (and any other anchor that calls `generate_reference`)

## Problem

Three stacked issues in `generate_reference`:

1. **TOCTOU race.** Two requests in the same millisecond both pass the
   "not exists" check and both insert. Saved by the `unique=True` on
   `reference`, but the caller sees a 500.
2. **Single-shot retry.** On collision the fallback is a UUID-suffix
   candidate; if *that* collides (rare but possible) there's no retry —
   straight to `IntegrityError`.
3. **`bulk_create` bypass.** `save()` is the only place references get
   set. `bulk_create([Payment(), Payment()])` inserts with `reference=""`,
   which violates `unique=True` on the second row. This is a real risk
   for the data-migration loaders.

## Proposed fix

Move reference generation to a `pre_save` signal so it fires on every
insert path, including `bulk_create`:

```python
@receiver(pre_save, sender=Payment)
def _set_payment_reference(sender, instance, **kwargs):
    if not instance.reference:
        instance.reference = generate_reference("PAY", model=sender)
```

Replace the single-shot UUID fallback with a small bounded retry loop
(N=5 attempts, each regenerating a candidate). After N collisions, raise
a typed error rather than a generic `IntegrityError`.

Long-term consider a Postgres `SEQUENCE` with a Python-side suffix to
sidestep collisions entirely; the signal approach is the minimum viable
fix.

## Acceptance

- `pre_save` signal stamps `reference` on `bulk_create` paths (test:
  `Payment.objects.bulk_create([..., ...])` produces two distinct
  references).
- Test: simulated collision retries and eventually succeeds.
- Loader regression: replay the data-migration `PaymentLoader` against a
  fresh DB and confirm no `IntegrityError` on duplicate references.

## Dependencies

Audit the other anchors that use `generate_reference` (Quotation,
Booking, …) and make sure the signal pattern covers them too.
