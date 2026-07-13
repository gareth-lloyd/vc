# SMELL-021 — `PriceBasis` defined twice with two competing authorities; loader silently defaults imported plans to GROSS

> ✅ **RESOLVED 2026-07-13** (local `main`, unpushed; merge `6cc64d8`, 3 units).
>
> - **Unit 1** — one `PriceBasis`: the duplicate in `pricing/enums.py` deleted;
>   the sole definition lives in `properties/enums.py` with a docstring
>   recording the authority split (engine → `RatePlan.price_basis` per BUG-009;
>   `prices_entered_as` → entry-form pre-fill only per GAP-035). **Deviation
>   from the ticket's proposed fix:** "keep it in pricing, import it into
>   properties" is the spine-illegal direction (properties may not import
>   pricing); the enum lives in `properties` and pricing imports it —
>   import-linter green.
> - **Unit 2** — `RatePlanLoader.transform` stamps `price_basis=GROSS`
>   **explicitly**. The "no per-villa basis signal" question is answered and
>   documented: legacy `RatesModel.Calculate()` always treats the entered rate
>   as the guest-facing gross (`GrossPrice = getWeeklyPrice`, net derived by
>   subtracting tax + commission) and no NET column exists anywhere in the
>   legacy schema — so *every* legacy plan is GROSS by rule, not by accident.
>   The feared "NET legacy villa imports as GROSS" case is structurally
>   impossible; no NET-import test exists because there is no NET input to
>   test. `reconcile_legacy` gains an invariant check (`SELECT 0` vs imported
>   plans carrying non-GROSS basis → BLOCKER on stamp regression; staff-created
>   NET plans excluded) + CUTOVER.md expected-gap row.
> - **Unit 3** — `prices_entered_as` marked non-authoritative at the field:
>   help_text + comments on `PropertySettings` and `PropertyDefaults`
>   (GroupSettings is gone — GAP-070), state-only migration `properties.0004`.
>   Chose document-over-derive: deriving it from the plan would invert the
>   pre-fill's purpose (it exists to seed plans that don't exist yet).

- **Severity:** 🟡 Smell (latent money bug — a NET legacy villa is mis-priced on cutover)
- **Source:** the 2026-07-02 backend complexity audit (pricing-authority divergence)
- **Files:** `pricing/enums.py:8–12`, `properties/enums.py:36`,
  `pricing/models/rate.py:30` (`RatePlan.price_basis`),
  `properties/models/settings.py:70` (`PropertySettings.prices_entered_as`)
  + `:133` (`GroupSettings`),
  `data_migration/loaders/pricing.py` (RatePlan create — omits `price_basis`),
  `data_migration/loaders/properties.py:258` (hardcodes `PriceBasis.GROSS`)

## Problem

"Is this villa's rate gross or net?" has two definitions and two authorities
that can disagree:

- `PriceBasis(GROSS/NET)` is declared **twice, identically** — `pricing/enums.py:8`
  and `properties/enums.py:36`.
- Two model fields consume it: `RatePlan.price_basis` (`rate.py:30`, which
  BUG-009/GAP-035 established as **the sole pricing authority** the engine
  branches on) **and** `PropertySettings.prices_entered_as` /
  `GroupSettings.prices_entered_as` (`settings.py:70,133`, demoted by GAP-035
  to "the new-season default / entry-form pre-fill").

The acute edge is at cutover: the legacy rate loader **never sets**
`RatePlan.price_basis`, so every imported plan takes the model default
(`GROSS`), while `properties/loaders` independently hardcodes
`prices_entered_as: PriceBasis.GROSS` (`properties.py:258`). If any legacy
villa was entered NET, the engine silently prices it **GROSS** on import —
the exact class of mis-pricing BUG-009 just closed, reintroduced via the
loader rather than the engine.

## Why it bites

Two enum definitions drift independently, and two "basis" fields can disagree
for one villa (engine trusts the plan; the settings serializer/entry form
pre-fills from settings). Today everything is GROSS so nothing is visibly
wrong — it hurts the first time a NET villa exists, and it hurts quietly
(a wrong owner/guest split, not an error).

## Proposed fix

- Collapse to **one** `PriceBasis` (keep it in `pricing`, import it into
  `properties` — the import spine allows pricing → properties direction).
- Make the legacy rate loader **carry the legacy basis onto
  `RatePlan.price_basis`** rather than relying on the model default; if legacy
  has no per-villa basis signal, decide and document the fallback explicitly
  (and reconcile it in `reconcile_legacy`).
- Confirm `prices_entered_as` is only a UI pre-fill (per GAP-035) and either
  rename/comment it as non-authoritative or derive it from the plan so the two
  can't diverge.

## Acceptance

- `PriceBasis` is defined once; `grep` finds a single class.
- The rate loader sets `RatePlan.price_basis` from legacy (or a
  documented, reconciled default); a test asserts a NET legacy villa imports
  as NET and the engine prices it NET.
- `reconcile_legacy` (or a one-off audit) reports zero plans whose basis was
  defaulted rather than derived.

## Dependencies

Sibling to BUG-009 (engine now honours `price_basis`) and GAP-035
(`price_basis` = sole authority, `prices_entered_as` demoted). Touches the
`data_migration` rate loader (see also the full-replace `--since` no-op noted
in the audit). Related smell family: SMELL-009 (duplication implemented N ways).
