# FG-018 — `total` means two different things in the quotation payload

- **Severity:** 🔫 Footgun (a contract that invites the wrong reading; it has
  already produced the same bug twice, once inside res and once outside it).
- **Found:** 2026-09-02, reviewing the Limitless quote Flow.

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
    "discount": "150.00"           // the operator discount, overwriting the engine's key
  }
}
```

Nothing in the payload signals which is authoritative. The nested one looks
more precise — it sits among `commission`, `tax`, `net_to_owner`,
`rate_subtotal`, the per-night array — so it is the one a reader reaches for.
It is the wrong one.

`pricing_snapshot["gross"]` and `pricing_snapshot["discount"]` are written by
`reservations/services/quotations.py:84-85`, *after* the engine has produced
the breakdown; line 85 clobbers the engine's own `discount` (its rate
reductions, Q-018) with the operator discount, while leaving `total` gross of
it. So within one dict, `total` is net of the engine's discount and gross of
the one sitting next to it.

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
   cheaper — `quotations.py:85` is the only writer. Does not fix `total`.
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
  `quotations.py:85` overwrites.
