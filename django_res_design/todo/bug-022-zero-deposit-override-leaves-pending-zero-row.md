# BUG-022 — A zero deposit override rewrites the PENDING deposit to 0.00 instead of removing it

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
