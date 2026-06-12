# BUG-010 — Refund self-approve permission conflicts with the SoD constraint

- **Status:** ✅ resolved (2026-06-12)
- **Severity:** 🔴 Bug
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `payments/services/refund.py:156–169`,
  `payments/models/refund.py:142–145`

## Problem

`RefundService.approve` lets the requester self-approve when they carry
`payments.self_approve_refund` (the `PERM_SELF_APPROVE` bypass at
`refund.py:156–164`), then unconditionally writes the actor:

```python
refund.approved_by = actor
refund.approved_at = timezone.now()
refund.save(update_fields=["approved_by", "approved_at", "updated_at"])
```

But the DB constraint is unconditional:

```python
models.CheckConstraint(
    condition=Q(approved_by__isnull=True) | ~Q(approved_by=F("requested_by")),
    name="refund_separation_of_duties",
)
```

So every *permitted* self-approval is a guaranteed `IntegrityError` → 500.
The model comment even admits the contradiction ("those rows must still land
with `approved_by IS NULL` until a distinct approver acts") — the service
ignores it.

## Proposed fix

Pick one side and make the other match:

1. **Drop the `PERM_SELF_APPROVE` bypass from `approve()`** (recommended).
   Separation of duties on *approval* stays a hard guarantee; keep the bypass
   on `execute()` only, where the DB deliberately doesn't constrain the
   executor.
2. Or make the constraint conditional (drop it / gate on a flag column) so
   the permission path can actually land rows.

Either way, delete or correct the misleading comment block on the constraint.

## Acceptance

- Test: requester with `payments.self_approve_refund` calling `approve()` on
  their own refund either gets a clean `PermissionError` (option 1) or a
  successfully APPROVED refund (option 2) — never an `IntegrityError`/500.
- Existing SoD tests (distinct approver OK, plain self-approve rejected)
  still pass.

## Resolution (2026-06-12)

Took option 1 (recommended). `RefundService.approve` now rejects the
requester unconditionally — `PERM_SELF_APPROVE` no longer enters the check,
so a permitted requester gets a clean `PermissionError` instead of tripping
the `refund_separation_of_duties` constraint into an IntegrityError 500.
The perm's bypass survives only in `execute()` (approver-may-execute),
where the DB deliberately doesn't constrain the executor.

The misleading comment block on the constraint (`payments/models/refund.py`)
and the stale `payments.refund.self_approve` perm strings in the service
docstrings were corrected to match. No schema change.

Test: `test_refund_approve__rejects_self_approval_even_with_self_approve_perm`
(`payments/tests/test_refund.py`) — written red (reproduced the
IntegrityError) before the fix. Existing SoD tests (distinct approver OK,
plain self-approve rejected, DB floor, execute bypass) unchanged and green.

Error typing stays bare `PermissionError` deliberately — that's SMELL-010's
scope.

## Dependencies

None. Related: SMELL-010 (the service signals rejections with bare
`PermissionError`/`ValueError`).
