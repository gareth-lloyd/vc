# GAP-099 — The Zoho financials block carries amounts but no payment status

> **✅ RESOLVED (2026-09-02, local `main` unpushed)** — shipped on `feat/gap-099`
> in 2 units (63f8540e code + tests, 356fe29d docs). `financials` now carries
> `deposit_status`, `deposit_due_at`, `balance_status`, `balance_due_at`
> alongside the eight amounts, read verbatim from `payment_component_splits`:
> status = raw `PaymentStatus` of the latest schedule row for that purpose
> (FAILED superseded by PENDING → `pending`; cancelled with schedule unpaid →
> `cancelled`, the CHECK-004 item-3 case), due_at = earliest `due_at` over
> non-terminal rows, ISO-8601. Keys always present, null-degrading. Decisions:
> raw enum over a derived `deposit_received` bool (Q2 — revisit only on
> pushback); `due_at` included (Q1 — resolves the GAP-085 `balance_due_at`
> open point). Built ahead of a Limitless ask on Gareth's go-ahead; the
> GAP-085 close-out records the contract extension. ⚠️ Tell Limitless the
> four keys exist and to switch their deposit-received test to
> `deposit_status == "succeeded"` (membership, not `!=`).

- **Severity:** 🟠 Gap (the CRM has to infer "has the deposit been paid?"
  from `status`, and gets it wrong).
- **Source:** 2026-09-02 review of the Limitless booking Flow
  (`limitless_insert_booking`) against `build_booking_payload`.
- **Files touched:**
  - `django_res/reservations/services/zoho_payload.py` —
    `_FINANCIALS_KEYS`, `_financials_payload`.
  - `django_res/reservations/services/owner_finance.py` —
    `payment_component_splits`, `ComponentSplit` (already carries `status`
    and `due_at`; both are dropped on the way into the payload).

## Problem

GAP-085's `financials` block sends eight **amounts** — gross/net/commission
for the deposit and balance components, plus the two totals. It sends
nothing about whether either component has actually been **paid**.

`ComponentSplit` already has the answer: `payment_component_splits` returns
`status` and `due_at` per purpose, and `_financials_payload` collapses the
splits keyed by purpose but reads only `gross`, `net_to_owner` and
`commission` from each. The status is discarded one line before it would
have been useful.

So the only payment signal in the whole booking payload is `status`
(`BookingStatus`), and consumers reverse-engineer payment state from it.
Limitless did exactly that, with a negative test:

```
if(payload.get("status").toString() != "awaiting_deposit")
{
    deposit_received = true;
}
```

which marks the deposit received on `draft`, `pending_owner_approval`,
`cancelled`, `expired` and `declined` — five states where no deposit was
taken (CHECK-004 item 3). A positive membership test over the five
"deposit has landed" statuses fixes *their* bug, but the inference itself is
the smell: `BookingStatus` is a workflow position, not a payment ledger, and
the two can legitimately disagree (a `deposit_paid` booking whose payment
later FAILED and is being re-collected; the GAP-087 deposit override minting
a superseding row).

`gross_deposit` compounds the confusion by looking like a settled figure. It
is the **scheduled** amount. Nothing in the payload says whether it arrived.

## Proposal

Add the status (and probably `due_at`) alongside each component, keeping the
GAP-085 contract: keys always present, degrading to `null` when there is no
schedule row — never an invented value.

```python
"deposit_status": _component("deposit", "status"),
"balance_status": _component("balance", "status"),
```

`_component` returns `None` when the purpose has no split, which is already
the right degradation. `status` is a raw `PaymentStatus` value, so it needs
excluding from the `f"{…:.2f}"` formatting `_component` currently applies —
either a second accessor or a formatter argument.

Open sub-questions:

1. **`due_at` too?** It is on `ComponentSplit` and would let the CRM show
   "balance due in 12 days" without a second call. Cheap to add; adds a
   field to the frozen contract.
2. **Raw enum values or booleans?** Every other enum in our payloads ships
   as the raw value with the mapping left to the Flow (`BookingStatus`,
   `ChargeCategory`, `EnquiryStatus`), so raw `PaymentStatus` is the
   consistent choice. A convenience `deposit_received: bool` would be easier
   for them and is what they actually want — but it is a derivation, and
   GAP-085's whole premise is that we send facts and Zoho derives nothing.
   Recommend raw status; revisit only if they push back.
3. **Does this supersede CHECK-004 item 3, or sit alongside it?** They
   should fix the inverted test regardless — this ticket removes the need to
   infer at all, but only once they consume the new fields. Sequence: they
   fix the test; we add the fields; they switch over.

Offered to Limitless in the 2026-09-02 email as an offer, not a commitment
— **do not build until they say they want it**, because it widens a contract
that was deliberately pinned on the 2026-07-29 call.

## Tests

- A booking with a PAID deposit and a PENDING balance → both statuses
  present and correct.
- A booking with no payment schedule → both `null`, amounts unchanged.
- A sparse imported snapshot → the whole block still `dict.fromkeys(...)`,
  new keys included.
- The pinned-contract test that asserts the financials key set needs its
  expected set extending (that test is the reason this is a deliberate
  change, not a drive-by addition).

## Related

- **GAP-085** the financials block this extends.
- **GAP-087** per-booking deposit override — the case where the scheduled
  deposit amount changes and a superseding row is minted.
- **CHECK-004** item 3, the consumer-side bug that surfaced this.
