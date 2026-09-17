# FG-018 — `total` means two different things in the quotation payload

- **Severity:** 🔫 Footgun (a contract that invites the wrong reading; it has
  already produced the same bug twice, once inside res and once outside it).
- **Found:** 2026-09-02, reviewing the Limitless quote Flow.
- **Status (2026-09-02): 🟨 partial** — options **2**, **3** and the
  docstring form of **4** landed with BUG-020 (`feat/bug-020`, 60a93d66 + 85fc6071 + 58acee82):
  `price_line` writes `pricing_snapshot["operator_discount"]` and leaves the
  engine's `discount` alone; `BookingService` nets `total`/`net_to_owner`
  from `line.total` at conversion; `_line_payload` /
  `build_quotation_payload` in `zoho_payload.py` now state which `total` is
  which on the wire. **Remaining:** option 1 — rename
  `pricing_snapshot["total"]` → `engine_total` when the snapshot shape is
  next touched (engine + stored JSON + FE schema).
  **2026-09-17:** the reprice half (BUG-025) is closed too —
  `BookingService.reprice_snapshot` nets `modify_dates` / `modify_guests`
  the same way, so no path writes the raw engine `total` to a booking.

## The trap

A `QuotationLine` exposes two keys called `total`, one nested inside the
other, meaning different things:

```jsonc
{
  "total": "1250.00",              // line.total — what the guest is quoted
  "discount": "150.00",
  "pricing_snapshot": {
    "total": "1400.00",            // engine total, BEFORE the operator discount
    "gross": "1400.00",            // ...the same number again
    "discount": "150.00"           // WAS the operator discount, overwriting the engine's
                                   // key — since BUG-020 it is the engine's again and the
                                   // operator figure is "operator_discount"
  }
}
```

Nothing in the payload signals which is authoritative. The nested one looks
more precise — it sits among `commission`, `tax`, `net_to_owner`,
`rate_subtotal`, the per-night array — so it is the one a reader reaches for.
It is the wrong one.

`pricing_snapshot["gross"]` and (originally) `pricing_snapshot["discount"]`
were written by `reservations/services/quotations.py` `price_line`, *after*
the engine had produced the breakdown; the `discount` write clobbered the
engine's own `discount` (its rate reductions, Q-018) with the operator
discount, while leaving `total` gross of it. So within one dict, `total` was
net of the engine's discount and gross of the one sitting next to it.
*(Fixed by BUG-020 unit 1, 60a93d66: the operator figure now goes to
`operator_discount` and `discount` is engine-only. `pricing_snapshot["total"]`
is still the pre-operator-discount engine figure on the line — that is the
half this ticket still tracks.)*

## Evidence that it is a real footgun, not a theoretical one

Two independent implementations read it wrong:

1. **Ours.** `BookingService` prefers `snapshot["total"]` over
   `quotation_line.total`, and books discounted quotes at the undiscounted
   price → **BUG-020**.
2. **Theirs.** `limitless_insert_quote` does exactly the same, in the same
   preference order (`snapshot.get("total")`, falling back to
   `line.get("total")`), and overstates every discounted quote in the CRM →
   **CHECK-005** item 2. The booking Flow repeats the pattern.

Both were written by people with the payload in front of them. Two out of two
readers picking the wrong key is a contract problem, not a competence one.

## Options

1. **Rename the snapshot key.** `pricing_snapshot["total"]` →
   `pricing_snapshot["engine_total"]`, keeping `gross` as-is. Clearest, but
   the snapshot is a stored `JSONField` on every historic line and booking, so
   it means either a data migration or a read-time shim — and the engine
   writes the key too (`pricing/services/engine.py:369`), so the blast radius
   reaches the pricing tests and the rate workbench.
2. **Stop overwriting `discount`.** Write the operator discount as
   `operator_discount` and leave the engine's `discount` alone. Fixes the
   *other* half of the collision (two meanings of `discount`) and is much
   cheaper — `price_line` is the only writer. Does not fix `total`.
   **Done (BUG-020 unit 1).**
3. **Net the discount into `total` at conversion**, so a *booking* snapshot's
   `total` is unambiguously the final figure even though a *quotation line*
   snapshot's is not. This is BUG-020's recommended fix; it removes the
   money bug but leaves the quotation-line payload as misleading as it is
   today, i.e. it does not help Limitless.
4. **Document it on the wire** — add a comment to `build_quotation_payload`'s
   docstring and, more usefully, say so explicitly in the integration notes we
   send out. Cheapest, weakest; the docstring is not what an integrator reads.

Recommend **(2) + (3) now** (cheap, and between them they fix both live
bugs), with **(1)** filed as the real repair whenever the snapshot shape is
next touched. **(4)** regardless — CHECK-005 already tells Limitless which
key to read, but the next integrator will not have had that email.

## Acceptance

- Whatever is chosen, a test asserts that the value a consumer would read for
  "what does the guest pay" equals `line.total` on a discounted line.
- `pricing_snapshot["discount"]` no longer means two things depending on who
  wrote it last.

## Related

- **BUG-020** — the money bug this caused inside res.
- **CHECK-005** item 2 — the same bug outside res.
- **Q-018** — rate reductions, the engine's own discount concept that
  `price_line` used to overwrite (fixed with BUG-020).
