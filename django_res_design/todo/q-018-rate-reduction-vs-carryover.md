> **🔎 INVESTIGATED + DESIGN DECIDED (2026-07-02)** — full codebase exploration
> and an adversarial design review done; remaining open questions answered
> (see below) and the field shape decided. **Implementation not started** —
> an 8-unit build plan (TDD, one commit per unit) is ready in
> `~/.claude/plans/ship-q-018.md`; the durable design content is all in this
> ticket. Headline: carry-over is already **built**
> (`pricing/services/carryover.py`) and copies prices verbatim, so the failure
> this ticket predicts is live; the fix is well-contained because the engine
> has a single price-derive point (`rule_nightly`).
>
> _Original ticket below, updated in place where facts had gone stale._

# Q-018 — Rate reductions: base price + reduction, so carry-over copies the base

- **Severity:** Question (design decision; carry-over correctness at stake)
- **Source:** 2026-06-11 new-villa setup transcript review
- **Files:** `pricing/models/rate.py` (`RateBand`, `rate.py:102-148` — the
  ticket predates SMELL-019's `RateRule`→`RateBand` rename),
  `pricing/services/carryover.py` (`RateCarryoverService.materialise()`,
  `:97-230`), `pricing/services/projection.py` (lazy twin),
  `pricing/services/rates.py` (`rule_nightly`),
  `django_res_design/04-pricing.md` (carry-over spec moved to `:271-293`;
  **note the whole doc still specs the dropped `RatePlan→RateCard→RateRule`
  model** — GAP-056/SMELL-019 never updated it), `pricing/models/discount.py`

## Problem

Today (legacy and new alike), a mid-season rate reduction is done by
**overwriting the price**. The loader then leaves a free-text note ("rate
reduced by 10% on 10 June") purely so that, when copying rates to next
season, she remembers to revert to the original — "the owners won't want
us copying over the reduced rates for the next season."

`RateCarryoverService.materialise()` (**built**, `carryover.py:97-230`)
clones the anchor year's bands verbatim — `apply_uplift(rule.nightly/weekly)`
at `carryover.py:159-160`, written at `:222-223`. If 2026 was discounted in
place, **2027 inherits the discounted price** — exactly the failure she
manually guards against. Her own design suggestion from the transcript:
"keep the original price and then apply a reduction to it."

The existing `Discount` model is promo-code/auto-apply oriented, not a
per-rate-rule price reduction, so it doesn't cover this as-is.

## Decided design (2026-07-02)

Model the reduction on `RateBand`: keep `nightly`/`weekly` as the **base**
price and add reduction fields. The pricing engine quotes the reduced price;
carry-over copies the base and drops the reduction. The free-text `notes`
ritual disappears.

**Field shape** — the ticket's single `reduction_amount` is ambiguous when a
band has *both* nightly and weekly bases, so:

- `reduction_percent` — Decimal(5,2), null; applies to both prices.
- `reduced_nightly` / `reduced_weekly` — Decimal(12,2), null; explicit **new**
  amounts, each strictly `<` its base and requiring that base to be set.
- `reduced_at` — DateField, null (the loader's "on 10 June"; FE prefills today).
- `reduction_reason` — CharField(200), blank.
- Percent and fixed amounts are mutually exclusive; both-null = no reduction.
  CheckConstraints (Meta, `__isnull`-explicit predicates): percent range
  0<p<100, percent-excludes-fixed, reduced-lt-base ×2, POA-excludes-reduction.

**Effective price is derived, never stored**: `RateBand.effective_nightly` /
`effective_weekly` properties (percent quantized to 0.01); `rule_nightly()`
(`pricing/services/rates.py:23-29` — the **single** quote-price derive point,
sole caller `engine.py:201`) switches to them, so every quote path picks up
reductions with one change. Carry-over and projection are then correct **by
construction** — their `_Band` dataclass / synthetic bands only read base
fields (`carryover.py:44-64`, `projection.py:234-243`) — but must be pinned
with the "discounted 2026 → undiscounted 2027" test. `RatePlanDuplicateView`
(`views/rate.py:85-88`, `pk=None` re-save) copies reductions verbatim **by
design** — a same-context copy tool; carry-forward is the cross-year path.
`VillaPricingSummary` min/max (`pricing/tasks.py:44-45`) should use effective
prices. `is_locked` (bulk-ops shield) is unaffected — reductions are
individual edits.

**Design hazards found by the adversarial review** (requirements, not nice-to-haves):

1. **NET-basis "before" total**: commission/tax gross-up scales with the base
   (`engine.py:285-295`, `_derive_commission_and_tax`), so a pre-reduction
   guest total must be computed by re-running the basis math on the un-reduced
   base — *not* by adding the subtotal delta to `total`.
2. **Fixed-mode silent no-op**: `rule_nightly` prefers `nightly`
   (`rates.py:25-28`), so `reduced_weekly` alone on a two-price band never
   changes a quote. Fixed reductions must cover **every** non-null base
   (serializer + FE enforced).
3. **Base-edit vs stored reduction**: PATCHing `nightly` below a stored
   `reduced_nightly` (exactly what the workbench MatrixCell inline editors
   send) would hit the DB constraint → must be a friendly serializer 400, not
   an IntegrityError.
4. **Audit trail**: the new money fields must join the
   `track(RateBand, ...)` AuditLog registration (`pricing/apps.py:48-61`) —
   untraceable reductions are what this ticket exists to kill.
5. Rounding: engine quantize is `ROUND_HALF_EVEN` (`engine.py:232`); pin a
   half-cent percent case, and the weekly-only `/7` double-quantization order.

**Staff surfaces (per decided OQ3)**: engine quote lines gain `reduced_from`
(base nightly, null when no reduction); the quote gains
`rate_subtotal_before_reduction` + `total_before_reduction` (null when equal),
passed through stay-options/occupancy-band shapes. FE: reduction editor in
`RateBandFormDialog` (with live effective-price preview), struck-through base
in the workbench matrix/timeline, "reduced from X" in the quote builder
(`quoteOptionSchema`/`stayRepriceSchema`/`occupancyBandSchema` — *not*
`stayOptionSchema`, which carries no money fields).

## Open questions (for the loader / product)

1. ~~Is a reduction always a % off the whole band, or sometimes a fixed
   amount or specific weeks only? (Specific weeks → split the band rather
   than complicate the model.)~~ **Answered** (Nick/Bryony, 2026-06-11
   email): a reduction is *usually* a % off certain still-available weeks,
   but *sometimes* a fixed (new) amount — "both options please" (Nick wants
   maximum pricing flexibility). So the model must support **both** a
   percentage reduction and a fixed-amount reduction, scoped to specific
   weeks/bands; for specific weeks → split the band. The customer also
   confirmed the base-price + reduction approach (so carry-over copies the
   base) is correct.
2. ~~Does a reduction apply to new bookings only from its date?~~
   **Answered (2026-07-02, code-confirmed):** yes, by construction — quotes
   and bookings snapshot the resolved nightly per line
   (`pricing/services/quote.py:9-32`, `Quotation.pricing_snapshot`,
   `Booking.pricing_snapshot` populated from `quote.breakdown`), so nothing
   re-derives historical prices; reductions affect new quotes only.
3. ~~Should sales see "reduced from X" in the quote builder, or just the
   effective price?~~ **Decided (2026-07-02):** yes — staff see "reduced
   from X" in both the rate workbench and the quote builder (a selling
   point for sales); guests see only the effective price.

## Acceptance

- Decision recorded in `10-decisions.md`; `04-pricing.md` updated (rewrite the
  rate-model + projection/carry-over sections to the as-built
  `RatePlan→RatePeriod→RateBand` naming while at it; errata note for the rest).
- Model fields + engine support + carry-over uses base price, with tests
  pinning "discounted 2026 → undiscounted 2027 carry-over".

## Build plan sketch (from the 2026-07-02 planning pass)

TDD, one commit per unit: (1) model fields + constraints + effective-price
properties + AuditLog tracking; (2) engine effective price + reduced-from
breakdown + summary rebuild + stay-options passthrough; (3) pin
carry-over/projection/duplicate semantics with tests; (4) serializer fields +
validation (hazards 2–3, clear `reduced_at`/`reason` on removal); (5) FE
schemas (`.nullable().optional()` to spare ~7 MSW fixture files) + reduction
editor in `RateBandFormDialog`; (6) FE workbench display (matrix strikethrough,
timeline `BandMeta.hasReduction`, probe `QuoteResultCard`); (7) FE quote
builder "reduced from"; (8) docs + Q-018 close-out. Deferred out of scope:
GAP-023 badges, bulk revert/season-wide fan-out UI, `Discount.card` repoint,
inline matrix editing of reduction values, full `04-pricing.md` refresh.

## Dependencies

Interacts with `RateBand.is_locked` semantics (unaffected — see above) and
GAP-023 (`gap-023-owner-approval-preview-lifecycle.md`, whose "unconfirmed
rates" badge surface is the natural future home for a reduced-rate badge;
deferred post-v1).
