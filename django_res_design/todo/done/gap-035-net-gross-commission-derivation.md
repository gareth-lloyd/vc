> **✅ RESOLVED (2026-06-22)** — The rate-band form now derives the net/gross
> counterpart on display. Staff type one figure, pick the plan's `price_basis`,
> and see the derived owner net (GROSS plan) or guest price (NET plan) live beside
> each price input, recomputing as they type — computed with the **same** mode-aware
> commission **+ tax** math as the engine's `04-pricing.md` steps 8-9 (percentage
> grosses up by `÷(1−pct)`, fixed commission flat both ways, tax skipped when
> exempt, `ROUND_HALF_EVEN`), so a band entered here prices identically at quote
> time. **Derive-on-display only** — the stored row is exactly the typed figure +
> `price_basis`, never the computed side (which the BUG-009 engine carve-out would
> otherwise re-derive and double-count). Derivation inputs come from
> `PropertyFinance.effective_commission()`/`effective_tax_policy()` resolved
> property→group, surfaced read-only on the **settings** endpoint (`commission`,
> `tax`, `prices_entered_as_effective`) beside `currency_code`.
> **Single-source-of-truth (Q1/the BUG-009 risk):** `RatePlan.price_basis` is the
> sole pricing authority; `PropertySettings`/`GroupSettings.prices_entered_as` is
> **demoted to the entry default** that pre-fills a *new* season's `price_basis`
> (`SeasonFormDialog`), no longer a second basis field. Q2 → `effective_commission()`
> resolution; Q3 → `ROUND_HALF_EVEN` (`roundHalfEven` mirrors `quantise_money`).
> Code: `properties/serializers/settings.py` + `views/settings.py`,
> `frontend/src/lib/pricing/netGross.ts`, `RateRuleFormDialog.tsx`,
> `SeasonFormDialog.tsx`; spec `04-pricing.md` (rate-entry subsection + updated
> authoritative-field note); decision row `10-decisions.md` (2026-06-22).
> **Residual:** the Booking owner-statement serializer still reads
> `prices_entered_as` for money — closed by the BUG-009 finance rewrite (reads
> `net_to_owner` from the snapshot, step 10), not by this ticket.

# GAP-035 — Net↔gross rate entry with automatic commission derivation

- **Severity:** Gap (data-entry tooling; pricing flexibility).
- **Source:** 2026-06-17 owner Loom (pricing walkthrough, 2:40–3:21).
- **Files:**
  - `django_res/pricing/models/rate.py` (`RatePlan.price_basis`, `RateRule`
    `nightly`/`weekly`)
  - `django_res/properties/models/finance.py`
    (`PropertyFinance.effective_commission()`)
  - design: `django_res_design/04-pricing.md` (rate-entry), `10-decisions.md`
  - FE rate-band form (under
    `frontend/src/features/properties/tabs/PricingTab.tsx`)

## Problem

Owners supply rates as **either net or gross**. Today staff pick `price_basis`
and hand-enter a single figure; there is no tool to convert between the two. The
owner wants **both, with automatic derivation**: "if a client only gives us net
rates… we put in 20% commission and it automatically calculates the gross
amount and organises it accordingly" — and the reverse for gross (take the
commission off to get net).

**Single-source-of-truth risk with BUG-009:** if this tool *persists* a derived
gross figure while the (deferred) BUG-009 engine fix later carves
commission/tax back *out of* gross at quote time, the commission is applied
twice. The entry layer and the quote-time engine must agree on one canonical
stored figure.

## Proposed direction

An **entry-time** helper on the rate-band form that, given the band's net (or
gross) amount + the effective commission % (`effective_commission()`), derives
the counterpart for **display/convenience** while storing a single canonical
figure plus `price_basis` and the commission % used. Lean towards
**derive-on-display** (don't persist the computed side) to avoid the BUG-009
double-count.

Keep this **distinct from** the quote-time carve-out/gross-up of BUG-009 — this
is about what the operator types; BUG-009 is about how the engine interprets it
— but both must use the **same** net↔gross math (the legacy
`RatesModel.Calculate()` formulas already transcribed in BUG-009) so a band
entered here prices identically there.

## Open questions

1. Store the derived figure, or derive-on-display only? (Lean derive-on-display
   to avoid the BUG-009 double-count.)
2. Which commission source when property- and group-level differ? (Use
   `effective_commission()`'s resolution.)
3. Rounding direction on the derived figure — reuse the existing
   `quantise_money()` ROUND_HALF_EVEN policy (see `done/smell-003`); ties into
   Q-023.

## Acceptance

- Decision recorded in `10-decisions.md`; `04-pricing.md` rate-entry section
  updated with the derivation rule and the chosen storage model.
- FE rate-band form behaviour specced (which field is canonical, when the
  derived value recomputes).

## Dependencies

- **BUG-009** — must use the same net↔gross math and agree on the canonical
  stored figure (else double-counting).
- `PropertyFinance.effective_commission()`.
- Q-023 (rounding of the derived figure).
