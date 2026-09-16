> **✅ RESOLVED (2026-08-07)** — Shipped on local `main` (ff `6fe42ea5`…`3bcfe33a`,
> 8 commits). Added a nullable `Booking.deposit_override_amount` (non-negative
> CHECK, audited) that `PaymentScheduler` honours at **both** write-sites —
> `create_for_booking` and, the durable path, `resync_for_booking`, which now
> also **mints** a PENDING deposit row when an override wants one and none is
> active (fixing the `deposit_required=False` / FAILED-deposit no-ops). A
> status-gated `Booking.set_deposit_override(amount, *, actor, reason)` (rejects
> once the deposit is settled; keys on booking status, honouring the
> reservations→payments layer ban) + a writer-gated `:deposit-override` staff
> endpoint + a FinanceTab set/edit/clear UI (en+el). Manual offline settlement
> (`:mark-paid` without a provider txn) was confirmed already complete — no
> rebuild. Splits + GAP-085 Zoho financials reshape automatically (derive-on-read,
> pinned by tests). Carry-over stays **manual** (free-text `Payment.notes` /
> `cancel_reason`); no automation, per the call. Two adversarial reviews (plan +
> backend diff); acceptance proven by an end-to-end cancel→rebook→override→
> mark-paid walkthrough. Deferred: percent/calc-type override, SD override, and
> FE-wiring the existing PENDING-edit `PATCH` (superseded by the durable override).

# GAP-087 — Per-booking deposit override + manual payment recording

- **Severity:** 🟢 Gap (operator flexibility — blocks the agreed
  cancellation carry-over workaround).
- **Source:** Limitless call 2026-07-29. Filed 2026-07-29. Philosophy per
  Limitless: "as much flexibility as possible" — full **manual**
  money-moving for cancel/rebook cases, explicitly NOT automated
  carry-over.
- **Files:**
  - `django_res/payments/services/payment_scheduler.py` — `_calc_amount`
    (~L242) sizes the deposit from
    `PropertyFinance.deposit_calculation_type`/`deposit_amount`
    (`effective_payment_schedule()`; policy fallback PERCENT 30,
    `properties/models/finance.py` ~L39-41). **Property-level only — no
    per-booking override exists.** `resync_for_booking` (~L156) re-derives
    the PENDING deposit from the same property policy on every
    `booking_total_changed`, so even a hand-tuned row would be clobbered.
  - `django_res/payments/services/manual_payment.py` —
    `ManualPaymentService.record`: operator-recorded rows behind the track
    POST, born PENDING (FG-012).
  - `django_res/payments/views/track.py` — `_track_action` (~L396):
    `:mark-paid` settles a PENDING row at an **operator-chosen** amount /
    paid_at / method (BANK_TRANSFER default) / reference — no
    payment-provider transaction involved.
  - `frontend/src/features/bookings/components/PaymentActionDialog.tsx` —
    mark-paid dialog, amount field pre-filled and editable.
  - `django_res/reservations/services/owner_finance.py` —
    `payment_component_splits` (~L153): derive-on-read over the live
    Payment rows.

## Problem

The call agreed a manual carry-over workaround for cancellations with
credit: cancel the old booking, create the new booking, **manually adjust
its deposit amount** (net of the carried-over credit), mark the deposit
paid. Today that flow dies at "adjust the deposit":

- Deposit sizing is a pure function of the **property's** finance policy —
  there is no per-booking override, and no API edits a PENDING row's
  amount.
- Worse, `resync_for_booking` recomputes the PENDING deposit from the
  property policy whenever the total moves (any charge-item edit), so a
  one-off adjustment has nowhere durable to live.

**Correction to the ticket's original premise** (verified 2026-07-29):
"record a manual/offline payment" largely **exists** — the track POST
(`ManualPaymentService.record`) creates rows, and `:mark-paid` settles at
an operator-chosen amount with no provider transaction, surfaced in the FE
mark-paid dialog. The genuine gaps are the **override** (sizing) and its
survival across resync — plus verifying the existing manual path composes
into the full carry-over flow.

## Proposed fix

1. **Per-booking deposit override** — `deposit_override_amount` (or
   amount-or-percent pair) on `Booking` (or on the schedule write surface),
   respected by `PaymentScheduler` at **both** creation
   (`create_for_booking`) and `resync_for_booking` (override wins over
   `effective_payment_schedule()`; balance stays the remainder). Staff API
   + audited.
2. **Manual/offline payment recording — verify and close gaps**: confirm
   the existing track POST + `:mark-paid` flow covers "carried-over credit
   marked as paid without a provider transaction" end to end (including
   the FE affordance on the deposit track), and fix whatever falls short —
   e.g. a notes/reference convention for "paid by carried-over credit".
3. **Splits flow-through — verify, don't build**: GAP-077
   `payment_component_splits` is derive-on-read over the live Payment rows,
   so an overridden deposit should reshape the deposit/balance split (and
   the GAP-085 Zoho block) automatically. Pin with a test.
4. **Nice-to-have (explicitly optional):** a structured "carried over from
   booking X" marker on the new booking — today the only home is free-text
   `Booking.cancel_reason` on the *old* booking
   (`reservations/models/booking.py` ~L182) and payment notes. Do not let
   this grow into carry-over automation; Limitless asked for manual
   flexibility, not workflow.

## Acceptance

- A booking with an override gets a deposit at the overridden amount;
  charge-item edits (total churn) resync the balance but **preserve** the
  override.
- Full carry-over walkthrough passes: cancel old booking → create new →
  override deposit → mark deposit paid (no provider txn) → splits + Zoho
  financials reflect the overridden figures.
- Audit trail on override set/clear; en+el for any new FE surface; quality
  gates green.

## Dependencies

- None hard. Coordinates: [GAP-077 ✅](gap-077-deposit-balance-gross-net-split.md)
  (splits must keep deriving correctly), GAP-085 (Zoho financials read the
  same source), GAP-086 (finance tab shows the same figures).
