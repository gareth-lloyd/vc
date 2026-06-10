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
