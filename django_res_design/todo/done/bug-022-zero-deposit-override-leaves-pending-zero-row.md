# BUG-022 — A zero deposit override rewrites the PENDING deposit to 0.00 instead of removing it

> **✅ RESOLVED (2026-09-03, local `main` unpushed)** — shipped on
> `feat/bug-022-023` with BUG-023: 0cf8dc44 carries the resync rule, the
> `deposit_required` gate and the FE changes; 861e206b adds the BUG-023 test
> pins; this commit is the docs close-out. **Fix:** `resync_for_booking` now
> computes one deposit target and a **zero target cancels** the PENDING deposit
> row via `transition_to(CANCELLED)` — event kind `DEPOSIT_NOT_REQUIRED` when no
> deposit is wanted, `DEPOSIT_COVERED` when committed money already covers the
> total — instead of resizing it to an unpayable 0.00. The row keeps its last
> amount for audit and frees the `unique_active_deposit_per_booking` slot, and
> the balance absorbs the whole total. The mint arm was generalised from
> "an override is set" to "a deposit is wanted and none is active", gated on the
> booking still being `AWAITING_DEPOSIT` **read from the DB** (not the caller's
> possibly-stale instance), so clearing a zero override brings the policy
> deposit back and a FAILED policy deposit is re-minted with a fresh `due_at`,
> while a WAIVED/REFUNDED deposit on an advanced booking never grows a rival.
> FE: the override dialog says "Enter 0 for no deposit on this booking", and
> `PaymentTrack` disables Mark received / Waive on a cancelled track (the
> backend has no PENDING row to action).
>
> ⚠️ **Tell Limitless:** Zoho `deposit_status` can now read `"cancelled"` on a
> **live** booking (one that wants no deposit), not only on a cancelled one —
> read `== "succeeded"` for "paid?", never `"cancelled"` for "booking dead?".
> The re-push timing itself is [BUG-021](../bug-021-zoho-booking-not-repushed-on-money-edits.md).
>
> ⚠️ **Left open:** a booking with no deposit row has no path out of
> `awaiting_deposit` — pre-existing, filed as
> [BUG-026](../bug-026-no-deposit-booking-parked-in-awaiting-deposit.md).

- **Severity:** 🔴 Bug (money workflow — the booking is stuck in
  `awaiting_deposit` behind a 0.00 row that cannot be marked paid).
- **Found:** 2026-09-02, by the `/ship gap-099` code review (verifier
  confirmed by reading `payments/services/payment_scheduler.py`; **not
  reproduced by test yet — write the failing test first**).

## Problem

`create_for_booking` documents that a zero override means "no deposit" and
gates on `deposit_amount > 0` (`payment_scheduler.py:~110`). The mint path
in `resync_for_booking` gates the same way (`minted > 0`, `:~246`). The
**resize** path does not: when a PENDING deposit row already exists,
`deposit.amount = quantise_money(_deposit_target(), …)` writes
`min(remaining, 0) = 0.00` and saves it, still PENDING, still occupying
`unique_active_deposit_per_booking` (`:~232`).

Zero is accepted end-to-end — the FE regex and the backend
`_parse_optional_money` only reject negatives — so a staff member POSTing
`:deposit-override {amount: "0"}` on a booking in `AWAITING_DEPOSIT` produces
a 0.00 PENDING deposit. `Payment.mark_paid` raises on `amount <= 0`, so the
booking cannot progress until an operator waives the row. The same override
set before confirmation yields no deposit row at all — two behaviours for
one input.

Only `test_create_for_booking__zero_override_creates_no_deposit_row` exists;
the resync path with a zero override is untested.

## Fix sketch

Pick one semantics and apply it on both paths. Recommended: a zero override
on resync **cancels** the PENDING deposit row (status → `cancelled`, the
same terminal the close-money receiver uses) and folds its amount into the
balance, so the schedule matches what `create_for_booking` would have built.
Alternatively reject `0` at the endpoint (`min_value` exclusive) — simpler,
but then "no deposit for this booking" has no expression at all.

Related: BUG-023 (same resync closure ignores `deposit_required`).
