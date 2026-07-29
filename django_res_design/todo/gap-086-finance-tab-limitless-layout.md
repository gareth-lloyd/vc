# GAP-086 — Booking finance tab: Limitless breakdown layout

- **Severity:** 🟢 Gap (UX restructure). Frontend-only, or nearly so.
- **Source:** Limitless call 2026-07-29 — Nick, seeing the Limitless Zoho
  booking layout: "we probably should break it down more like this". Filed
  2026-07-29.
- **Files:**
  - `frontend/src/features/bookings/tabs/FinanceTab.tsx` — the booking
    finance tab. Today: `SnapshotSection` renders the engine-shape rows
    (nightly rate / rate subtotal / extras / fees / adjustments / discount /
    commission / tax / deposit / balance / security / total, ~L75-86),
    `PaymentSplitSection` renders the GAP-077 per-component table
    (gross/commission/tax/net per deposit & balance, ~L160), then the manual
    charges section.
  - `frontend/src/features/bookings/schemas.ts` — `PaymentComponentSplit` /
    `BookingNetToOwner` already typed on the booking detail.
  - `django_res/reservations/services/owner_finance.py` —
    `payment_component_splits` (~L153) + `owner_money_for_booking`: the
    backend data source (already exposed as `payment_splits` /
    `net_to_owner` on the staff booking detail, GAP-077).

## Problem

The finance tab presents the **engine's** decomposition
(subtotal → extras → discount → commission → tax → grand total) with the
component split as a secondary table. Limitless/Nick want the **money-flow**
decomposition as the primary shape — the same one the Zoho booking module
uses (and that GAP-085 now pushes):

- Total gross / total net
- Gross deposit / net deposit / deposit commission
- Gross balance / net balance / balance commission
- Security deposit

## Proposed fix

FE restructure of `FinanceTab` to lead with the Limitless shape:

1. **Header pair:** total gross (`net_to_owner.gross_total` /
   `booking.total`) and total net (`net_to_owner.net_to_owner`).
2. **Deposit triplet / balance triplet:** map straight off
   `payment_splits` rows — `gross`, `net_to_owner` (net), `commission` per
   component. Tax stays visible (our net is gross − commission − tax;
   don't silently fold tax into "commission").
3. **Security deposit row:** the snapshot key
   (`security`/`security_deposit`) and/or the SD track. Verify what the
   booking detail actually exposes for a live `SecurityDeposit` row and
   extend the API surface if the policy/track figure isn't already there —
   the backend model + `PropertyFinance.security_deposit_*` policy exist,
   exposure is the only question.
4. Keep the engine snapshot rows available (collapsed/secondary section, or
   below the fold) — they answer "why is the gross what it is", the new
   layout answers "who pays what when". Keep the GAP-077 drift caveat.

Backend work only if step 3 finds a gap; everything else reads existing
fields (GAP-077 `payment_component_splits` + the security-deposit track).

## Acceptance

- Finance tab leads with total gross/net, deposit gross/net/commission,
  balance gross/net/commission, security deposit — matching the GAP-085
  Zoho block figure-for-figure (same source, `payment_splits`).
- Engine breakdown still reachable; component tests updated; en+el i18n.
- Quality gate green (frontend; backend too if API exposure was extended).

## Dependencies

- [GAP-077 ✅](done/gap-077-deposit-balance-gross-net-split.md) — the data.
- **GAP-085** — sibling, not a dependency: same figures, other consumer.
  Land the mapping vocabulary (which res field feeds which label) once and
  reuse it in both.
