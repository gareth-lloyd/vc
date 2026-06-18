> **✅ RESOLVED (2026-06-18)** — Two remainders from the SD percent-base fix.
> **Part 1 (dead `calculate_from`):** dropped. `_size_sd` always sizes a percent
> SD against the charges-inclusive booking total, and legacy did the same — its
> `CalculateFrom` basis was ignored (`ResService.cs:2519-2526`). The field/enum
> were removed from the finance models, effective policy, serializer, audit
> registration, data-migration loader and SPA schema (migration
> `properties/0018`). Commit `d641bee`.
> **Part 2 (no SD resync on later charges):** `resync_for_booking` filters to
> DEPOSIT/BALANCE, so a charge added after the SD row existed never resized it.
> Added `SecurityDepositService.resize_for_booking`, hooked on the same
> `booking_total_changed` receiver as the schedule resync; it re-derives a
> percent SD but only while still AWAITING_DETAILS/AWAITING_BT — once
> PRE_AUTHED/HELD the figure is committed at the provider, so the move is logged
> as a `RESIZE_SKIPPED` event instead. The merged GAP-015 modify path rides the
> same signal, so modifies resize the SD for free. Commit `1e52b70`.
>
> _Original ticket preserved below for context._

# GAP-019 — security deposit sizing ignores `calculate_from`; no resync on charges

- **Severity:** Gap
- **Source:** booking-charge-items review fixes (2026-06-10)
- **Files:** `django_res/payments/services/security_deposit.py` (`_size_sd`),
  `django_res/properties/models/finance.py` (`security_deposit_calculate_from`)

## Problem

Two remainders after the percent base was fixed to use the charges-inclusive
booking total (same base as the deposit/balance schedule):

1. **`security_deposit_calculate_from` is dead config.** The field exists on
   `PropertyFinance`/`GroupFinance` (nightly / weekly / total_stay), is ported
   by the data-migration loader and editable via the finance API, but
   `_size_sd` never reads it — percent SDs always size against the total.
   Either implement the nightly/weekly bases (needs a nights/weeks derivation
   from the booking dates) or drop the field; check what legacy actually did
   with it before choosing.

2. **No SD resync on charge changes.** `resync_for_booking` deliberately
   filters to DEPOSIT/BALANCE purposes, so a charge added *after* the SD row
   is created never resizes it (the fix only helps charges that exist at
   creation time). Resizing a live SD is not a simple row update — it may
   already be pre-authed at the provider — so this needs its own design:
   probably only resize while the SD is still AWAITING_DETAILS/AWAITING_BT.
