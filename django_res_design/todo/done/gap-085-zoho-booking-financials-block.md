# GAP-085 — Zoho booking financials block (replace null placeholder)

> **✅ RESOLVED (2026-07-29)** — built as specced (4 TDD units on
> `feat/gap-085`): 8-figure `financials` block (2dp strings) sourced from
> `owner_money_for_booking` / `payment_component_splits` — the FinanceTab
> authority — with explicit degrade (sparse snapshot → all null; no
> schedule → component figures null; never invented zeros); **top-level**
> `extras[]` (engine snapshot extras then manual charge lines, each
> `{label, amount, commissionable, category: null}` — category waits for
> GAP-088); cancelled-booking figure pins; `zoho_send_sample --person-pk`
> (CommandError on unknown/ANONYMIZED, empty-optional-fields report kept)
> plus money-rich booking-picker requirements. Payload re-read carries
> `with_charges_total` + `property__finance` + payments/charge_items
> prefetch (query pin 5→7).
>
> **Flag for the 2026-08-12 call:** (a) this ticket's "nothing zeroes
> money" claim was wrong for the split path — cancelling a booking with
> unsettled PENDING rows terminates them, so the authority (and FinanceTab)
> report **0.00** deposit/balance components; the push agrees byte-for-byte
> rather than inventing pre-cancellation figures, and the booking-level
> pair still carries the money for reporting. Confirm Limitless is happy
> reading 0.00 components on such cancellations (the alternative — null
> instead of authority zeros — is a one-branch change). (b) `extras` rides
> as a **sibling** of `financials`, not inside it. The open contract points
> below still stand for that call.
>
> **Extended by GAP-099 (2026-09-02)** — the block now also carries each
> component's payment state, because Limitless were inferring "deposit
> paid?" from `BookingStatus` and getting it wrong (CHECK-004 item 3):
> `deposit_status`, `deposit_due_at`, `balance_status`, `balance_due_at`.
> `*_status` is the raw `PaymentStatus` of the **latest** schedule row for
> that purpose (a FAILED deposit superseded by a fresh PENDING re-collection
> reports `pending`; a booking cancelled with its schedule unpaid reports
> `cancelled`). The full vocabulary is `pending`, `processing`, `succeeded`,
> `failed`, `refunded`, `cancelled`, `expired`, `waived` — any of the eight
> can appear, so consumers should test membership, not `!=` one value.
> `*_due_at` is the earliest `due_at` among that purpose's non-terminal
> rows, ISO-8601 with offset (e.g. `2026-10-01T12:00:00+00:00`). Same
> degrade posture as the amounts: keys always present, `null` on a sparse
> snapshot or when the purpose has no schedule rows, never invented. Values
> are the FinanceTab authority's (`payment_component_splits`) verbatim.
> This resolves the `balance_due_at` open contract point below.

- **Severity:** 🟢 Gap (integration contract — the booking push works, but
  carries no money).
- **Source:** Limitless call 2026-07-29 (Villa Collective / Limitless
  stakeholder call). Filed 2026-07-29. GAP-082 deliberately shipped
  `"financials": None` pending exactly this call.
- **Files:**
  - `django_res/reservations/services/zoho_payload.py` —
    `build_booking_payload` emits the explicit `"financials": None`
    placeholder (~L379; rationale in the module docstring ~L66-71).
    `_line_payload` (~L230) carries only aggregate `total`, `discount` and
    the raw `pricing_snapshot` — no itemized extras anywhere in any payload.
  - `django_res/reservations/services/owner_finance.py` —
    `payment_component_splits` (~L153): GAP-077 derive-on-read per-component
    (deposit/balance) gross/commission/tax/net over the live Payment rows;
    per-component rounding is half-even with the exact residual landing on
    the **last** component (BALANCE).
  - `django_res/integrations/management/commands/zoho_send_sample.py` —
    fold-in (d): the contact picker (`_pick_person`, ~L241) prefers-but-
    relaxes agency/country/tags/relationships and has no way to pick a
    specific person; `add_arguments` (~L70) only knows `--dry-run`.

## Problem

GAP-082's booking push sends `financials: null` — key presence pinned the
contract position, content was deferred to this call. The call resolved it:

Zoho's booking module has formula fields, and Limitless initially proposed we
send only the "left column" (total gross, gross deposit, net deposit) with
Zoho deriving the rest. **That only works if commission is proportional
across deposit/balance — and ours is not**: non-commissionable extras
(GAP-076) pass through outside the commission base, and GAP-077's allocation
puts the rounding residual entirely on BALANCE. A Zoho-side pro-rata formula
would silently disagree with res by a few cents (or worse, on
extras-heavy bookings). Decision: **res sends every figure explicitly**;
Zoho's formula fields are not relied on for anything we can compute.

The call also required extras to be **itemized separately** with their
commissionable flags, with category labels consistent between the two
systems (dropdown + free-text fallback — the taxonomy itself is GAP-088).

## Proposed fix

1. **`financials` object, all figures explicit** (money as strings, like
   `_line_payload`):
   - `total_gross`, `total_net`
   - `gross_deposit`, `net_deposit`, `deposit_commission`
   - `gross_balance`, `net_balance`, `balance_commission`
   Source = `payment_component_splits` (+ `owner_money_for_booking` for the
   booking-level pair) — the same authority the FinanceTab split table reads,
   so res-UI and Zoho can never disagree. Booking with no owner money
   (sparse imported snapshot) or no schedule: degrade explicitly (nulls with
   the keys present), never invent zeros — same posture as the GAP-082
   placeholder.
2. **Itemized `extras[]`**: one entry per `BookingChargeItem`
   (`reservations/models/charge_item.py` — free-text `label`, signed
   `amount`, `commissionable`) plus the engine-applied pricing extras from
   the snapshot. Each entry: `label`, `amount`, `commissionable`,
   `category`. `category` becomes a stable enum value once **GAP-088** lands
   (`BookingChargeItem` has no category column today); until then send the
   free-text label and omit/null the category key — do not fake a taxonomy.
3. **Cancellation test**: pin that a CANCELLED booking pushes with the
   **full** financials block intact (call decision: push
   `status=cancelled` and leave the figures for reporting — already true
   structurally, `build_booking_payload` has no status gate and nothing
   zeroes money; the test stops a future "helpful" regression).
4. **Fold-in — `--person-pk` on `zoho_send_sample`**: Limitless colleague
   Greg needs ONE live contact post with relationships, tags, and agency
   (+agency country) populated to finish the Zoho-side field mapping. The
   picker prefers those but silently relaxes them; add a `--person-pk` flag
   so the curated rich contact can be posted deliberately.

## Open contract points — pin with Limitless (next call 2026-08-12)

- **Gross is post-discount.** `line.total` is already net of the operator
  discount (`quotations.py` ~L89: `max(gross - discount, 0)`) — Zoho must
  not subtract a discount field from it again.
- **Which discount figure feeds their field:** operator `line.discount` vs
  the engine promo discount inside `pricing_snapshot["discount"]` vs the
  sum — they are different numbers living in different places. *(Update
  2026-09-02, BUG-020: the operator figure now also rides inside the
  snapshot as `pricing_snapshot["operator_discount"]`, so both are
  addressable by key; `discount` is engine-only again.)*
- **Security deposit:** absent from the Zoho layout read out on the call.
  Res has a first-class track (`payments/models/security_deposit.py` +
  `PropertyFinance.security_deposit_*` policy) — does it get a Zoho field?
- **`balance_due_at`:** where does it fit in their layout (was already an
  agenda item). **Resolved by GAP-099 (2026-09-02):** shipped inside
  `financials` as `balance_due_at` (with `deposit_due_at`), ISO-8601.

## Acceptance

- Booking push carries the 8-figure `financials` block, byte-agreeing with
  `payment_component_splits` / FinanceTab; deposit + balance figures sum to
  the booking figures (residual on BALANCE, per GAP-077).
- `extras[]` itemized with commissionable flags; category rides once
  GAP-088 lands.
- Cancelled-booking full-figures test green.
- `zoho_send_sample --person-pk N` posts exactly that contact (still
  reporting its empty optional fields).

## Dependencies

- **GAP-088** (charge-item category taxonomy) — **soft**: the `category` key
  upgrades from free-text/null to enum when it lands; nothing here blocks
  on it.
- [GAP-082 ✅](done/gap-082-zoho-villa-push.md) / [GAP-081 ✅](done/gap-081-zoho-flow-outbound-push.md)
  — push machinery + booking payload already on `main`. No hard
  dependencies.
