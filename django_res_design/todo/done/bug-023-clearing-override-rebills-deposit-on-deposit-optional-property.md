# BUG-023 — Clearing a deposit override re-bills a deposit on a property that requires none

> **✅ RESOLVED (2026-09-03, local `main` unpushed)** — shipped on
> `feat/bug-022-023` with BUG-022: 0cf8dc44 carries the `deposit_required`
> gate and the resync rule, 861e206b adds the policy pins, and this commit is
> the docs close-out. **Fix:** the policy
> branch of the resync deposit target returns `Decimal("0")` when
> `deposit_required` is false, mirroring `create_for_booking`; the zero target
> then cancels the PENDING deposit row per BUG-022, so clearing an override on
> a deposit-optional property returns the schedule to BALANCE-only instead of
> re-billing the policy percentage. The gate landed inside BUG-022's commit
> because that commit widened the mint arm, which would otherwise have grown a
> policy deposit on a deposit-optional property; this ticket's own commit adds
> the pins. **Decided along the way:** property deposit policy is **live** for
> unsettled schedules — flipping `deposit_required` off cancels a PENDING
> deposit on the next resync, flipping it on mints one while the booking is
> still `AWAITING_DEPOSIT`.
>
> ⚠️ **Tell Limitless:** Zoho `deposit_status` can now read `"cancelled"` on a
> **live** booking (one that wants no deposit), not only on a cancelled one —
> read `== "succeeded"` for "paid?", never `"cancelled"` for "booking dead?".
> The re-push timing itself is [BUG-021](bug-021-zoho-booking-not-repushed-on-money-edits.md).
>
> ⚠️ **Left open:** a booking with no deposit row has no path out of
> `awaiting_deposit` — pre-existing, filed as
> [BUG-026](bug-026-no-deposit-booking-parked-in-awaiting-deposit.md).

- **Severity:** 🔴 Bug (money — the customer is asked for a deposit the
  property's policy forbids).
- **Found:** 2026-09-02, by the `/ship gap-099` code review (verifier
  confirmed by reading `payments/services/payment_scheduler.py`; **not
  reproduced by test yet — write the failing test first**).

## Problem

`create_for_booking` only creates a deposit when
`override is not None or schedule.get("deposit_required")`
(`payment_scheduler.py:~110`). The resync's `_deposit_target()` closure
(`:~220`) has no equivalent: with no override it falls straight to the
policy percentage, regardless of `deposit_required`.

Before GAP-087 this was unreachable — a `deposit_required=False` booking
never had a PENDING deposit row for resync to resize. GAP-087's mint path
(`:~240`, whose own comment notes it is "the only path that materialises a
deposit for a `deposit_required=False` booking") makes it reachable:

1. `PropertyFinance.deposit_required=False`, total 1400 → create: BALANCE
   1400, no DEPOSIT.
2. Set override 500 → resync mints DEPOSIT 500, BALANCE 900. Correct.
3. **Clear** the override → resync finds the PENDING deposit, override is
   `None`, policy branch returns `min(1400, 30% × 1400) = 420` → DEPOSIT 420,
   BALANCE 980. The property never asked for a deposit.

`test_clearing_override_reverts_to_policy` runs only on the
`deposit_required=True` fixture.

## Fix sketch

In `_deposit_target()`, when `override is None` and the policy has
`deposit_required` false, return `Decimal("0")` — and then handle the zero
target the same way BUG-022 decides (cancel the PENDING deposit row, fold
into balance), so clearing an override on such a property returns the
schedule to its pre-override shape. Test on a `deposit_required=False`
fixture: set then clear → BALANCE 1400, no active DEPOSIT.

Related: BUG-022 — fix together; both live in the same closure and both
need a "zero deposit target on resync" rule.
