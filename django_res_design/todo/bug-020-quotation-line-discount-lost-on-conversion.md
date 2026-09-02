# BUG-020 — A quotation line's discount is dropped when the quote converts to a booking

- **Severity:** 🔴 Bug (money — the guest is quoted one figure and booked at
  a higher one).
- **Found:** 2026-09-02, while reviewing the Limitless quote Flow. The Flow
  makes the *same* mistake against the same two keys (CHECK-005 item 2),
  which is what prompted the check on our side.
- **Confirmed by probe**, not by reading: a temporary test against
  `POST /api/v1/quotations/{pk}:convert` — see "Reproduction" below.

## Problem

`QuotationLine` carries two different totals:

| value | meaning |
| --- | --- |
| `pricing_snapshot["total"]` | the **engine** total, *before* the operator discount |
| `pricing_snapshot["gross"]` | same figure, written alongside it (`quotations.py:84`) |
| `pricing_snapshot["discount"]` | the operator discount, **overwriting** whatever the engine put in that key (`quotations.py:85`) |
| `line.total` | `max(gross − line.discount, 0)` — **what the guest is quoted** (`quotations.py:89`) |

`BookingService` reads the wrong one:

```python
# reservations/services/bookings.py:83
total = cls._decimal(snapshot.get("total", quotation_line.total))
```

`snapshot["total"]` is present on every engine-priced line, so the
`quotation_line.total` fallback never fires. Nothing in `bookings.py`,
`services/charges.py` or `services/owner_finance.py` re-applies
`line.discount` afterwards, and the booking's own `pricing_snapshot` is
`dict(quotation_line.pricing_snapshot)` — so the pre-discount `total` is
carried onto the booking too, and every downstream money surface inherits it:

- `Booking.balance_due`
- `owner_money_from_snapshot` → `gross_total`, and therefore `net_to_owner`,
  the FinanceTab authority, and the GAP-085 `financials` block pushed to Zoho
- the payment schedule (deposit/balance are derived from the booking total)

The guest is quoted the discounted figure on the rendered quote
(`quotation_render.py:130` reads `line.discount` correctly) and then invoiced
the undiscounted one.

## Reproduction

Confirmed 2026-09-02 with a throwaway test appended to
`reservations/tests/test_api_quotations.py` (create a line with a discount,
`send()`, then `:convert`):

```
line.total            1250.00     <- quoted to the guest
line.discount          150.00
snap['total']         1400.00     <- pre-discount engine figure
snap['gross']         1400.00
snap['discount']       150.00
booking.balance_due   1400.00     <- BOOKED AT THE UNDISCOUNTED PRICE
booking snap['total'] 1400.00
```

7 nights @ £200 = £1,400 gross, £150 discount, £1,250 quoted, £1,400 booked.

## Why it survived

- `QuotationLine.discount` is well covered *within* the quotation domain —
  `test_create_line_with_discount_reduces_total` and
  `test_discount_clamps_total_at_zero` both pass, and the clone service
  carries `discount` correctly. No test crosses the conversion boundary with
  a non-zero discount.
- The hand-rolled `_snapshot` helper in `test_api_bookings.py:34` builds
  `total = rate + extras − discount + commission + tax`, i.e. it *assumes*
  `total` is already net of discount. That is the **engine**'s convention for
  its own reductions (Q-018), and it is the convention `owner_finance`
  quietly relies on. `quotations.py:85` breaks it by overwriting the same key
  with the operator discount while leaving `total` gross of it. So the
  booking-side tests model a snapshot shape that quotation-side code never
  produces, and both sides pass.

## Fix

The one-line version is to stop preferring the snapshot:

```python
total = cls._decimal(quotation_line.total)
```

`line.total` is the authoritative post-discount figure and is always
populated. But **do not stop there** — the booking's `pricing_snapshot` is
still the pre-discount blob, so `owner_money_from_snapshot` keeps returning
the inflated `gross_total` and the FinanceTab / Zoho figures stay wrong even
once `balance_due` is right.

Options for the snapshot itself:

1. **Net the discount into the copied snapshot at conversion** — set
   `snapshot["total"] = line.total` on the `dict(...)` copy, leaving `gross`
   and `discount` intact as provenance. Smallest change; keeps one meaning
   for `total` on a *booking* snapshot (net of everything), which is what
   `owner_finance` and `_snapshot` already assume.
2. **Teach `owner_money_from_snapshot` to subtract `discount`.** Rejected:
   it would double-subtract engine reductions, which are already inside
   `total`.

Recommend (1). It also resolves half of FG-018.

## Tests

- Convert a discounted line → `booking.balance_due == line.total`. (the
  probe above, promoted to a real test)
- Convert a discounted line → `owner_money_for_booking(booking)["gross_total"]`
  equals the discounted total.
- Convert a discounted line → the payment schedule's deposit + balance sum to
  the discounted total.
- The GAP-085 `financials.total_gross` on a discounted booking matches the
  quote the guest accepted.
- A zero-discount line is unchanged (regression floor for every existing
  booking-money test).

## Blast radius

Any booking converted from a discounted quotation line since the quotation
domain shipped. Worth a one-off report over existing rows —
`QuotationLine.objects.filter(discount__gt=0, is_selected=True)` joined to
their bookings — before deciding whether historic bookings need correcting or
just flagging. **Do that before fixing**, so the query still finds them.

## Related

- **FG-018** — the two-keys-named-`total` footgun that caused this, and
  caused the same error in the Limitless quote Flow.
- **CHECK-005** item 2 — the external instance of the identical mistake.
- **SMELL-020** — the `booking_total()` money authority; this is the input to
  it being wrong, not the authority itself.
