# GAP-074 — Nightly / flexible quoting: nightly-price quoting for no-fixed-changeover villas, per-line flexible stays, and the odd-length composition rule

> **Scope widened 2026-09-16 (todo consolidation):** absorbs **GAP-075**
> (per-quote-line ad-hoc flexible stay — reuses this ticket's renderer, could
> not start before it) and **Q-023** (partial-week / nightly price composition
> — the rule this ticket renders); each one's full text is kept as a "Merged
> from" section at the end. One owner call gates all three: the agenda is
> under **Owner call agenda** below. Suggested landing order: Q-023's docs +
> 10/15-night tests (can go ahead of the call) → GAP-074 → GAP-075.

- **Severity:** 🟢 Gap (new quoting surface) — the per-night data exists in the
  engine, but no output path renders it. Cross-stack (backend stay-options + FE
  builder + guest email).
- **Source:** 2026-07-08 Nick / Gareth res-rebuild call. Nick: Kenya / Patmos
  villas have no fixed changeover; the best way to sell them is to give the
  client the **full available date range + a nightly price** and let them do
  their own date maths — possibly with **multiple price bands** across the range
  where rate periods change. ~95% of quotes stay weekly blocks; this is the
  minority path.
- **⚠️ Product gate — needs owner/Debbie call before build.** Nick wants to run
  the two-tier (weekly-block *vs* nightly) presentation past Debbie: the concern
  is guest confusion when one quote mixes weekly-priced and nightly-priced
  options. Also open: is nightly the *default* for no-changeover villas or an
  opt-in, and do we standardise all options in an email to one style?
  *(2026-07-29: the Q-023 odd-length-composition confirmations D1–D3 go on
  this same call's agenda — same nightly-pricing territory, one owner ask
  instead of two. Since 2026-09-16 they are written out under **Owner call
  agenda** below; the round they came from is retired to
  [reviews/](reviews/owner-questions-2026-07-02.md).)*
- **Files touched (best-guess):**
  - `django_res/reservations/services/stay_options.py` — `StayOptionsService`;
    no-changeover branch prices the requested dates as-is (`_plan_blocks`
    returns `[], 0, None` when `ChangeoverService.required_weekday()` is `None`,
    ~L392); `weekly_prices` explicitly *defers* flexible villas (returns
    `changeover_day=None, weeks=[]`, ~L434).
  - `django_res/pricing/services/engine.py` — engine already yields one
    `QuoteLine(nightly=…)` per night (~L161-208); `RateBand.nightly` /
    `RatePlan.fallback_nightly` supply per-night rates.
  - `django_res/reservations/services/quotation_render.py` — email/preview
    context; today emits `nights` + block `total` per line, no nightly rate
    (~L104-116).
  - `frontend/src/features/quotations/` — `schemas.ts` (`stayOptionSchema` /
    `quoteOptionSchema` parse `total`/`nights`, no per-night field),
    `QuoteResultLine.tsx`, `StayOptionPicker.tsx` (week strip).
  - `django_res/comms/templates/comms/quotation.sent.body.mjml` — per-line row.

> **📌 Carried over from GAP-078 (resolved 2026-07-12):** the quote email's
> **weekly-vs-nightly section break** lands with this ticket. GAP-078 shipped
> the country/region grouping (`line_groups` + `show_group_headers` in
> `build_quotation_context`, group loops in BOTH `quotation.sent.body.mjml`
> and `quotation_quote.html`) — when nightly lines exist, partition within or
> above those geo groups and omit any empty section. Remember: every mjml body
> edit needs a companion `comms/000N_seed_*` migration, and MJML compilation
> HTML-escapes `>` inside Django tags (compute booleans in Python).

## Problem

For a `changeover_day = any` property, the builder can only quote the exact
requested dates as a single option; there is no way to present "available from
D1 to D2, £X / night" and let the client pick their own dates. Every consumer
renders a block/stay **total** — the nightly rate is computed by the engine but
never surfaced — and `weekly_prices` skips flexible villas, so the timeline
strip is blank for them too. Nick's preferred sell for these villas (whole
available range + nightly price, banded across rate periods) is unbuildable
today.

## Proposed fix

1. Add a nightly-range stay option to `StayOptionsService` for no-changeover
   villas (and, once [GAP-075](done/gap-075-per-line-flexible-min-nights-override.md)
   lands, any line flagged flexible): resolve the maximal available window
   around the requested dates, split it at `RatePeriod` boundaries into one or
   more nightly-priced segments (reuse the canonical flattener /
   `covering_bands`), each carrying `nightly`, `date_from`, `date_to`, `nights`,
   `currency`, POA flag.
2. Extend the `search-options` contract + FE schemas with a `nightly_range`
   option kind alongside the existing block options; render it in
   `QuoteResultLine` as a date-range row with a per-night price (multiple
   sub-rows when the range spans price bands).
3. Extend the quote line + render context so a saved nightly-range line emails
   as "Available DD Mon – DD Mon · £X / night" (multi-band → multiple lines),
   grouped under the flexible/nightly section from
   [GAP-078](done/gap-078-quote-property-ordering-country-region.md).
4. Presentation decision (product): standardise all options in an email to one
   style, or show a weekly-block vs nightly section break (see GAP-078).

## Acceptance

- A no-changeover property in the builder offers a nightly-range option showing
  the full available window + per-night price, split into segments where rate
  periods change. (service + component test)
- Saving it stores a nightly-priced line that renders in the quote email with a
  nightly rate and date range. (test)
- Weekly-block villas are unaffected; the engine single-block contract is
  unchanged.
- Quality gate green both stacks.


## Owner call agenda (owner + Debbie)

Collected 2026-09-16 so the one call settles everything this ticket and its
merged halves need. Record answers in `../design/decisions.md` and here.

### Agenda item: two-tier presentation (GAP-074)

- Does mixing weekly-block and nightly-priced options in one quote confuse
  guests? (Nick's concern, to put to Debbie.)
- For no-changeover villas, is nightly the **default** or an opt-in?
- Do we standardise all options in one email to a single style?

### Agenda item: odd-length stay composition (D1–D3, was Q-023)

You raised nightly pricing for odd bookings (10–15 nights that don't fit
week blocks) and worry about rounding. Rounding is settled — everything is
computed to the penny with bankers' rounding — so this is just confirming
the composition rule matches what you'd expect.

**D1 — How a non-whole-week stay is priced.**
Current rule: every night is priced at that week's weekly price ÷ 7, and the
nights are added up. So a 10-night stay spanning two rate weeks = 7 nights
at the first week's rate ÷ 7 + 3 nights at the second week's ÷ 7. The
alternative would be "1 × full weekly price + 3 nights at a separate nightly
rate". Suggested: **keep the current rule** — it never surprises anyone when
a stay crosses a season boundary. OK?

**D2 — When you've set an explicit nightly price.**
Where a period has its own nightly price entered, that price is used for the
nights (instead of weekly ÷ 7). Confirm that's the behaviour you want.

**D3 — Any floor on odd lengths?**
Each villa's minimum-nights rules always apply. Beyond that, is there any
blanket rule like "never quote under 5 nights", or is villa minimum-nights
the only guard? Suggested: **villa minimum-nights only**.

**On answer (D1–D3):** bless current engine behaviour in `04-pricing.md` + pin
10/15-night tests — docs/tests can proceed ahead of the answer; the answers
only confirm.

## Dependencies

- **Product:** owner/Debbie call on two-tier presentation — blocks build.
  Agenda below.
- Merged **GAP-075** (per-line flexible/min-nights override; the ad-hoc
  late-season case reuses this nightly-range renderer) — lands after the
  GAP-074 renderer.
- Builds on **GAP-030** (weekly-prices timeline — extend to flexible villas)
  and merged **Q-023** (partial-week / nightly composition; rounding +
  fallback already done; docs + tests can land ahead of the call).
- Feeds **GAP-078** (section grouping weekly vs nightly).

---

## Merged from GAP-075 — Per-quote-line ad-hoc flexible stay (min-nights + nightly)

> _Folded in 2026-09-16 (todo consolidation). The standalone ticket is closed as
> [GAP-075](done/gap-075-per-line-flexible-min-nights-override.md); the text below is that ticket as it stood, headings
> demoted one level. A reference to GAP-075 elsewhere now means this section._

- **Severity:** 🟢 Gap (new per-line override). Cross-stack.
- **Source:** 2026-07-08 Nick / Gareth res-rebuild call. Nick: even villas with
  an official fixed changeover will, late in the season or when gaps appear,
  "go flexible from now on, with a minimum" — staff need to offer a flexible
  nightly stay on a *specific quote* without changing the property's standing
  changeover config.
- **Files touched (best-guess):**
  - `django_res/reservations/models/quotation.py` — `QuotationLine` (~L220-278)
    has no `is_flexible` / `min_nights` / nightly fields; the only escape hatch
    is `is_manual` + operator-typed `total` + `price_override_reason` (a flat
    figure, not a nightly rate or a date-range-with-min-nights construct).
  - `django_res/reservations/services/stay_options.py` /
    `django_res/pricing/services/engine.py` — reprice path; min-nights today is a
    property/period concept only (`PropertySettings.min_nights_rental`,
    `RatePeriod.min_nights`, strictest-wins in `_validate_periods_against_stay`).
  - `frontend/src/features/quotations/` — `schemas.ts`
    (`quotationLineWriteInputSchema` ~L387), `StayOptionPicker.tsx` /
    `QuoteResultLine.tsx`, `SaveQuoteDialog.tsx`.

### Problem

There is no way to mark a single quote line as "flexible arrival, min N nights,
priced nightly" independent of the property's changeover day. Min-nights is a
property/period concept; the only per-line override is a flat manual total —
no nightly rate, no min-nights, no date-range semantics.

### Proposed fix

- Add an operator affordance on a fixed-changeover result to "quote flexibly"
  for this stay: sets a per-line flag + min-nights, then prices via the
  [GAP-074](gap-074-nightly-price-quoting-no-changeover.md) nightly-range path
  within the true available window (respecting the ad-hoc min-nights, not the
  property changeover).
- Persist the flag + min-nights on `QuotationLine` (nullable, default off) so
  the saved quote and its email render as a nightly/flexible option.
- The reprice contract carries the override so the engine ignores changeover
  alignment for that line only; all other quotes and the property config are
  untouched.

### Acceptance

- An operator can flip a fixed-changeover result to a flexible nightly quote
  with a min-nights, priced within the true available window, without touching
  property config. (component + service test)
- The property's standing changeover behaviour and every other quote are
  unaffected. (test)
- Quality gate green both stacks.

### Dependencies

- Depends on **GAP-074** (nightly-range renderer + engine path).
- Related **SMELL-024** (QuotationLine / quotation-view god-object — keep the
  override thin).

---

## Merged from Q-023 — Partial-week / nightly price composition for odd-length stays

> _Folded in 2026-09-16 (todo consolidation). The standalone ticket is closed as
> [Q-023](done/q-023-partial-week-nightly-composition.md); the text below is that ticket as it stood, headings
> demoted one level. A reference to Q-023 elsewhere now means this section._

- **Severity:** Question (pricing correctness for non-whole-week stays).
- **Source:** 2026-06-17 owner Loom (pricing walkthrough, 3:21–4:01).
- **Files:**
  - `django_res/pricing/services/rates.py:23` (`rule_nightly` —
    `nightly = weekly/7` derivation, the single derive point)
  - `django_res/pricing/services/engine.py` (per-night line assembly)
  - `django_res/pricing/models/rate.py` (`RateBand.nightly`/`weekly`)
  - design: `django_res_design/04-pricing.md` (engine steps), `10-decisions.md`

> **2026-07-29 refresh:** `RateRule` is now `RateBand` (SMELL-019), and Q-018
> added base + reduction fields with derived `effective_*` — all still quoted
> through the same `rule_nightly` derive point, so the composition question
> below is unchanged. **Overlap note:** GAP-074/075 build the nightly *output*
> path (nightly-range quoting for no-changeover / ad-hoc-flexible villas);
> this ticket's D1–D3 confirmation questions should ride the GAP-074
> owner/Debbie call rather than a separate ask — see
> [gap-074](gap-074-nightly-price-quoting-no-changeover.md) and
> [owner-questions-2026-07-02.md](reviews/owner-questions-2026-07-02.md).

### Problem

Pricing is week-block oriented; the owner needs **nightly pricing for "odd
bookings over 10–15 days outside the week block"** and is worried about
**decimals / rounding up or down**.

Two of his three concerns are **already resolved**:
- Money rounding policy is `quantise_money()` / ROUND_HALF_EVEN
  (`done/smell-003`).
- No-rate-for-a-night fill is `RatePlan.fallback_nightly` (`done/gap-008`).

The genuinely-open piece is the **partial-week composition rule**: how a stay
that isn't a whole number of weeks is built from `weekly` and `nightly` rows.
Today the engine prices **per night** — deriving `nightly = weekly/7` (quantized
to 0.01) when only `weekly` is set — and sums the nights. The question is
whether that matches owner expectation, versus, e.g., N×weekly + remainder
nights at an explicit nightly rate.

### Proposed direction

Document the partial-week algorithm explicitly in `04-pricing.md`:
- Confirm whether an explicit `RateBand.nightly` always **wins over** the
  `weekly/7` derivation for sub-week remainders.
- State how full-week + remainder stays combine (per-night sum vs
  N×weekly + remainder×nightly).
- Keep rounding on the **existing** ROUND_HALF_EVEN per-night policy — do **not**
  re-open `smell-003`. Frame the owner's rounding worry as "verify the current
  policy meets expectation," not "define a new one."

### Open questions

1. Per-night quantize-then-sum (current behaviour) or quantize-the-stay-total?
2. Does an explicit `nightly` override `weekly/7` for sub-week remainders?
3. Any minimum-night threshold before nightly pricing applies?

### Acceptance

- Decision recorded in `10-decisions.md`; `04-pricing.md` engine steps state the
  partial-week composition rule.
- Engine tests pin a representative 10- and 15-night partial-week quote.

### Dependencies

- Existing `nightly`/`weekly` on `RateBand`; `rule_nightly`
  (`pricing/services/rates.py:23`).
- `done/smell-003` (rounding — reuse, don't reopen), `done/gap-008`
  (`fallback_nightly`).
- GAP-035 (rounding of the derived net↔gross figure); Q-018 (base+reduction —
  resolved; effective prices derive through `rule_nightly`).
- [GAP-074](gap-074-nightly-price-quoting-no-changeover.md) /
  [GAP-075](done/gap-075-per-line-flexible-min-nights-override.md) — the nightly
  quoting surfaces this composition rule feeds.
