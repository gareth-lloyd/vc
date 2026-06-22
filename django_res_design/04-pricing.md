# 04 — Pricing

The pricing app is a pure library: given a property, dates, party size, and currency, return a Quote. It has no knowledge of bookings, enquiries, or payments — those import from here.

## File layout

```
pricing/
├── enums.py
├── models/
│   ├── __init__.py
│   ├── currency.py     # Currency, FxRate
│   ├── rate.py         # RatePlan, RateCard, RateRule
│   ├── extra.py        # Extra
│   ├── discount.py     # Discount
│   ├── changeover.py   # ChangeOverRule
│   └── summary.py      # VillaPricingSummary (signal-rebuilt cache)
├── services.py         # PricingEngine, FxConverter, AvailabilityService
├── signals.py
└── tasks.py            # Celery: rebuild summaries, refresh fx
```

## Currency

### `Currency(TimestampedModel)`
- `code` — CharField(3, unique) — ISO 4217
- `name`, `symbol`
- `decimal_places` — PositiveSmallInteger(default=2)
- `is_active` — bool

### `FxRate(TimestampedModel)`
Append-only.
- `base` — FK Currency PROTECT
- `quote` — FK Currency PROTECT
- `rate` — DecimalField(18, 8)
- `as_of` — DateField

Constraint: `UniqueConstraint(base, quote, as_of)`.

## Rate model

Three levels: **RatePlan → RateCard → RateRule**. Each level carries the metadata that its scope owns.

- `RatePlan` — the operator's "Season". Names the period, owns currency and price basis, no prices.
- `RateCard` — the operator's "rate card". The unit of editing in the admin UI: has name, min/max nights, and is what `Discount` rules attach to. (Changeover is property-level, not card-level — GAP-007.)
- `RateRule` — the price row. One per (date sub-range × party-size band) inside a card. Occupancy bands are sibling rules sharing date range with different `(min_party, max_party)`.

This three-level split honours the operator mental model (see `product-design/03-workflows.md` flow 13) without re-introducing the legacy `VillaSeasonDate` table — date ranges live on `RateRule`. Production data confirms this is the right shape: 96% of legacy seasons had a single date range; only 3% of rate rows had occupancy bands, so a separate band table is unjustified.

**Why seasons stay per-property.** The mockup-demo (2026-05-29) explored standardising seasons across the portfolio (VC-defined peak/shoulder/low) and splitting Season→Inclusions→Rates into separate layers. We deliberately **keep the per-property shape**. The operator's driver for "how many seasons a villa has" is **service inclusions**: a villa needs multiple `RatePlan`s only when what's included changes across the year (e.g. high season bundles a private chef; low season doesn't). Where inclusions are constant year-round, one plan suffices regardless of rate variation — high/mid/low price differences live in sibling `RateCard`s within a plan. `RatePlan.inclusion` stays the descriptive field; there is **no** first-class `Inclusion` entity and **no** portfolio-wide standard-season catalogue (it would fight the 96%-single-range finding for a reporting convenience with no named consumer yet). VC-standard reporting *labels* (peak/shoulder/low) are wanted but their placement — most likely on `RatePlan`, not `RateCard` — is an open follow-up (`10-decisions.md`). See `10-decisions.md` "Seasons stay per-property; inclusions drive how many a villa has".

**Lifecycle.** Every rate model is `AuditedModel` only. Retiring a plan/card/rule is done by toggling `is_active=False` (already on `RatePlan` / `RateCard`) or by setting `effective_to` to a past date (`RateRule.date_from`/`date_to` already bound applicability). Historical bookings keep their pricing via `Booking.pricing_snapshot`, so a previously-active rate that is now switched off does not retroactively change any booking's recorded price. Hard delete is permitted for "rule entered in error" cases (no FK from `Booking` to `RateRule` — bookings reference only their snapshot).

### `RatePlan(AuditedModel)`
Groups a set of cards; replaces legacy `VillaSeason` as the grouping container. Carries no prices.
- `property` — FK properties.Property PROTECT
- `name` — CharField (e.g. "Summer 2026", "2026 Agent Net")
- `currency` — FK Currency PROTECT
- `price_basis` — TextChoices (`GROSS`, `NET`) — gross is customer-facing, net is agent. **Owner-facing views must show net.** The legacy build leaked **gross** figures onto the owner booking-confirmation (a "big low moment a couple of weeks in", 2026-06-08 demo) — a genuine logic bug, not a config gap. The rebuild closes it: `PricingEngine` derives commission/tax `price_basis`-aware (GROSS carve-out vs NET gross-up — Services steps 8-9, BUG-009) and computes `net_to_owner` explicitly (step 10), and owner-facing serializers read that field directly rather than recomputing. Treat "owner confirmation shows net" as an acceptance criterion, not an implementation detail. **Engine status:** the mode-aware branch is *specified* here but its **code is deferred to the finance rewrite** — today's engine always adds commission/tax on top, which over-charges the (currently universal) GROSS plans; see `todo/bug-009-price-basis-ignored-by-engine.md`.
- `effective_from` — DateField
- `effective_to` — DateField(null=True, blank=True) — open-ended
- `is_active` — bool
- `notes` — TextField(blank=True)
- `inclusion` — TextField(blank=True) — free-text "what's included" copy (e.g. chef, daily housekeeping)

### `RateCard(AuditedModel)`
The operator-facing rate-card unit; the level at which length-of-stay rules and discounts attach. Has no prices of its own — those live on child `RateRule`s. Changeover is **not** a card-level concern — it resolves from the property (`PropertySettings.changeover_day` chain + `ChangeOverRule` windows) only (GAP-007).
- `plan` — FK RatePlan CASCADE
- `name` — CharField (e.g. "Peak weeks", "Shoulder")
- `description` — TextField(blank=True)
- `min_nights` — PositiveSmallInteger(default=1)
- `max_nights` — PositiveSmallInteger(null=True, blank=True)
- `sort_order` — int(default=0)
- `is_active` — bool(default=True)
- `notes` — TextField(blank=True)

Index: `(plan, sort_order)`.

> **Seasonal minimum-stay drops need no extra field.** Villas commonly require 7
> nights in high season but drop to 3 (occasionally lower) outside it
> (2026-06-08 demo). This is expressed as different `min_nights` on the relevant
> season's cards — the per-card LOS rule already varies by season because cards
> are season-scoped. The same demo flagged changeover-day + length-of-stay +
> rate interplay as the genuinely hard corner of pricing ("quite a lot of
> complexity… we've run into all those problems and limitations and know how to
> solve them"); the three-level RatePlan→RateCard→RateRule split plus
> property-level changeover (GAP-007) is the answer, but treat the rates/products
> walkthrough with the person who loads rates (Ashley) as a required validation
> pass before locking the pricing UI.

### `RateRule(AuditedModel)`
The fundamental price row. Replaces `VillaSeasonRate` × `VillaOccupencyPrice` × `VillaSeasonDate`.
- `card` — FK RateCard CASCADE
- `date_from` — DateField
- `date_to` — DateField
- `min_party` — PositiveSmallInteger(default=1)
- `max_party` — PositiveSmallInteger
- `nightly` — Decimal(12, 2, null=True, blank=True)
- `weekly` — Decimal(12, 2, null=True, blank=True)
- `is_poa` — BooleanField(default=False)
- `is_locked` — BooleanField(default=False) — preserves the rule against bulk recompute / re-import. Bulk services (any future "regenerate rates for season X" admin action, CSV re-import, FX-driven mass adjustment) skip locked rules. Individual edits via the admin / API are unaffected and clear the lock implicitly only when the operator confirms in the UI. Replaces the legacy `IsManualUpdate` flag from `workflows/04-pricing/rates.md`.
- `is_approved` — BooleanField(default=True) — gates engine visibility. Staff-created rules default to `True`; bulk-imported rules land as `False` and require an explicit approval pass before `PricingEngine.quote()` will consider them. Replaces the legacy `IsApprove` workflow step.
- `notes` — TextField(blank=True)

> **No `is_provisional` / `carried_over_from`.** Next-year quoting is solved by
> *lazy projection* (see "Projected pricing for future years" below), which derives
> a guide rate at quote time and writes no rows — so there is no per-rule
> "provisional" flag to carry. Earlier drafts added both fields for a
> materialise-everything carryover design; that was superseded (`10-decisions.md`
> row 50) before either field was built.

Constraints (Postgres):
- `CheckConstraint(date_from <= date_to)`
- `CheckConstraint(min_party <= max_party)`
- `CheckConstraint(nightly IS NOT NULL OR weekly IS NOT NULL OR is_poa)` — must have a price or be POA
- `EXCLUDE USING gist (card_id WITH =, daterange(date_from, date_to, '[]') WITH &&, int4range(min_party, max_party, '[]') WITH &&)` (`raterule_no_overlap`) — within-card overlap (inclusive dates × party brackets) is forbidden unconditionally; disjoint occupancy bands on the same dates remain legal siblings. Cross-card overlap is allowed and resolved by **card order** (`sort_order`, then `pk`) at quote time — the first card with a covering rule wins. There is no per-rule precedence field: legacy had no precedence concept to mirror (its overlap winner was an unordered `TOP 1`), and the data-migration loader resolves legacy overlaps at load time (`data_migration/CUTOVER.md` "Rate rule overlap resolution").

Index: `(card, date_from, date_to)`.

`RateRuleSerializer.validate()` mirrors all of the above (including the
EXCLUDE overlap, with inclusive-range semantics) so API writes that would
violate a constraint return `400 field_errors` rather than a 500
`IntegrityError`. On partial update it merges incoming attrs with the stored
row; on create, omitted fields fall back to model defaults. Adjacent rules
must therefore start the day **after** the previous rule's `date_to` — the
admin UI's "Add rule" / "Save & add another" seeding does this automatically.

#### Occupancy bands
A card with multiple party-size bands is represented as **multiple `RateRule` rows** sharing a `card_id` and date range, with disjoint `(min_party, max_party)` intervals. The `EXCLUDE` constraint permits this because party range is part of the exclusion tuple. No separate band table.

> **Confirmed high-priority requirement (2026-06-08 demo).** Occupancy-bracket
> pricing — different nightly/weekly rates for, e.g., 1–8 / 9–12 / 13–16 guests,
> *also varying by season* — was singled out as an important element **missing
> from the legacy build**, where the quote generator "defaults to the higher
> price" (legacy in fact fell back to base-weekly ÷ 7 on a bracket miss — see
> `09-departures.md` "Legacy correctness bugs explicitly fixed" #2). The
> sibling-`RateRule` shape above **is** this feature and it is first-class here,
> not an edge case. Caveat the production-data finding accordingly: the "only 3%
> of legacy rate rows had occupancy bands" number (above) measures legacy
> *under-support*, **not** future demand — the owner explicitly wants occupancy
> brackets used far more widely. The separate-band-table decision still stands
> (sibling rules are sufficient); just don't read the 3% as "occupancy pricing is
> rare / unimportant."
>
> **The engine resolves one bracket; the *builder* may present several.**
> `PricingEngine.quote()` resolves the single `RateRule` whose `(min_party,
> max_party)` contains the inquiry's party size (and raises `PartyOutOfRange`
> otherwise) — it does **not** auto-emit a price line per bracket. Showing a
> client multiple occupancy options is a deliberate **quote-builder** action by
> the agent, not an automatic fan-out: per the demo, agents are *selective* about
> what they send and set the filters from their own knowledge rather than dumping
> every bracket (Gareth asked whether the UI should present all options for all
> party sizes; the owner said no — the salesperson curates). So the
> matched-not-fallen-back engine behaviour is correct as designed; multi-bracket
> display, where wanted, is composed by the builder calling the engine once per
> party size.
>
> **Superseded by owner (Loom 2026-06-17) — default is now fan-out, not curate.**
> The owner reversed the "salesperson curates / no automatic fan-out" *default*:
> for an occupancy-priced property the quote builder should present **all**
> covering bands as separate lines **checked by default** ("better to quote all
> of the occupancy-based pricing to give them full visibility of what the price
> could be if the group size changes"), and the agent *deselects* the ones not
> wanted. The prior rationale is retained above for context — it was about the
> *default*, and the new default inverts it. **Engine contract is unchanged:**
> `PricingEngine.quote()` still resolves one bracket per call; the *builder*
> drives the fan-out (call once per covering band, or a small `:bands` endpoint).
> Tracked in [`todo/gap-044-occupancy-band-fanout-builder.md`](todo/gap-044-occupancy-band-fanout-builder.md).

#### Disjoint date ranges within a card
A card whose price applies to multiple non-contiguous date ranges is represented as multiple `RateRule` rows sharing `card_id` and party range, with disjoint date intervals.

## Projected pricing for future years

At this time of year clients inquire for *next* year, but only ~10% of next-year rates are
confirmed — so quoting next year is slow manual work, and owners are slow to return rates.
Legacy handled this by hand: rename last year's season, shift its dates, copy each rate over.
The rebuild solves it with **lazy projection**: when a quote lands on a year with no
`RatePlan`, the engine *derives* a guide rate at quote time from the most recent year that has
rates, flags the quote, and **writes nothing**. No speculative rows; always fresh, never stale;
2028/2029/2030 answered from one code path. This is an M1 feature (`11-milestones.md`) and the
stated highest-value time-saver (`10-decisions.md` row 50). Materialising editable rows is a
separate, on-demand action — see "Carrying a year forward" below.

### `pricing.services.RateProjectionService`

```python
class RateProjectionService:
    @staticmethod
    def find_anchor_plan(property, currency, date_from, date_to) -> RatePlan | None: ...

    @classmethod
    def project(cls, *, property, date_from, date_to, currency,
                date_map=shift_to_changeover_weekday,
                uplift=Decimal("0")) -> PricingContext | None: ...
```

- **Anchor** = the most recent active `RatePlan` for the property+currency whose
  `effective_from` is before 1 Jan of the requested year. Restricting to an earlier year both
  guarantees a forward projection and stops a partial same-year plan (or a previously
  materialised carry-forward) from anchoring on itself. `None` for a brand-new villa with no
  prior rates → the engine raises `NoRateAvailable` as usual.
- **`project`** clones the anchor's active cards and `is_approved=True` rules into **unsaved**
  in-memory instances whose `pk` is the source row's pk, packaged as a `PricingContext` the
  engine prices exactly like a real one. Because the synthesized rows carry the source pks, the
  quote breakdown (`QuoteLine.rule_id`, `winning_card_id`) points at the real anchor rows for
  free traceability — and nothing is written. Rule date ranges move via `date_map`, preserving
  the night count (`map_range`); the plan envelope moves by calendar year. Prices scale by
  `1 + uplift`.
- **Verbatim by default** (`uplift = 0`): the guide shows last year's number unchanged. The
  parameter exists so a future `SystemSettings` escalator can feed a standard uplift, but no
  settings plumbing is built — anything non-zero must be an explicit, signed-off figure.

#### Date mapping — `date_map` *(open follow-up, now on the read path)*

A rule's `date_from`/`date_to` must move into the target year. Two candidate rules; the source
conversation (2026-05-29) does **not** settle which the business wants:

- `shift_to_changeover_weekday` (default) — preserve the changeover weekday, so a
  Saturday-to-Saturday week stays Saturday-to-Saturday in the new year (the start aligns to its
  weekday; the end follows by the original span). Matches how villas with a `ChangeOverRule`
  actually let.
- `keep_calendar_date` — keep the same calendar dates, just relabel the year.

The function is injected (defaulting to weekday alignment), so nothing is hard-coded — but note
the default now gates the **default quoting path**, not just an occasional clone, so it matters
more than under the old carryover-only design. Confirm against Bryony's listing Loom before
treating it as settled (`10-decisions.md` open follow-up "Carryover date-mapping rule").

### Engine behaviour for projected quotes

`PricingEngine.quote()` first resolves a real plan covering the stay (`_load_real_context`); a
real `RatePlan` must span the whole `[date_from, date_to)`, so a quote resolves exactly one
plan and **real always beats projected** — projection only fills a genuine gap. When no real
plan covers the stay it falls through to `RateProjectionService.project()`; if that also yields
nothing it raises `NoRateAvailable` as before. The `allow_projection=False` kwarg forces the
hard `NoRateAvailable` for callers that must not price on a guide (e.g. a booking-time guard).

A projected quote carries `Quote.is_projected=True` and
`Quote.breakdown["is_projected"] = True` plus `Quote.breakdown["projection"]` (source plan id,
source/target year, uplift, date-map name), so the quote generator and the outbound quotation
email render the "2028 — 2027 rates shown as a guide, inquire for accurate pricing" marker. The
flag and provenance persist into `QuotationLine.pricing_snapshot` / `Booking.pricing_snapshot`
so a later reader can see the quote was built on a projection and from which year.

### Carrying a year forward (on-demand promote)

When staff want **editable** rows for a year — an owner returned real numbers, or they want to
hand-tune the guide before confirming — `pricing.services.RateCarryoverService.materialise(
property, *, target_year, currency, date_map=…, uplift=…)` clones the anchor year into real
`RatePlan` / `RateCard` / `RateRule` rows, reusing the same `date_map` + `uplift` as projection
so the materialised rows match the guide a quote would have shown. Date-mapping can land
adjacent source ranges on top of each other (a leap-year span crossing Feb 29; the weekday map
shifting neighbours in opposite directions); rules claim date space in ascending source-pk
order — the same precedence `pick_rule_for_night` gives colliding in-memory projected rules —
with later rules keeping every remainder segment around earlier claims (a mid-punched rule
splits into two rows). The materialised plan therefore prices every night exactly as the
projection would have, and `raterule_no_overlap` can never fire. It is idempotent per
`(property, currency, target_year)` (a plan already starting in that year is returned
untouched), records provenance in `RatePlan.notes`, and raises `NoRateAvailable` when there is
no prior year to carry from. Materialised rows are ordinary editable rules staff then
confirm/adjust — there is no per-rule "provisional" flag.

It is exposed as a `RatePlan` admin action ("Carry forward to next year") and a
`POST /properties/{id}/seasons:carry-forward` endpoint. It is **deliberately not** a Celery
beat task — nothing rolls the whole portfolio forward speculatively. This supersedes the manual
`:COPY` only as the *default*; manual ad-hoc copy stays for arbitrary cloning
(`workflows/04-pricing/seasons.md`).

## Extras

### `Extra(AuditedModel)`
Property-scoped catalogue of named charges that get added at quote time: cleaning fee, pet fee, heating, linen, extra-bed fee, resort fee, etc. Replaces (a) what the product UX calls "extras", and (b) the obsoleted `Surcharge(kind=CLEANING|SERVICE_FEE|RESORT_FEE)` slot in earlier drafts.

Tax and commission are **not** Extras — they live on `properties.PropertyFinance.TaxPolicy` and `properties.PropertyFinance.Commission` (per `03-finance-config.md`) and are read by the pricing engine via the `PropertyFinance.effective_*` resolvers.

- `property` — FK Property CASCADE
- `name` — CharField (e.g. "End-of-stay cleaning", "Pet fee", "Heating")
- `description` — TextField(blank=True)
- `kind` — TextChoices (`CLEANING`, `PET_FEE`, `HEATING`, `LINEN`, `EXTRA_BED`, `SERVICE_FEE`, `RESORT_FEE`, `OTHER`)
- `calc` — TextChoices (`FIXED_PER_STAY`, `FIXED_PER_NIGHT`, `FIXED_PER_PERSON`, `FIXED_PER_PERSON_PER_NIGHT`, `PERCENT_OF_SUBTOTAL`)
- `amount` — Decimal(12, 2)
- `currency` — FK Currency PROTECT
- `is_mandatory` — BooleanField(default=True) — when False, only applied if the caller explicitly opts in at quote time
- `applies_from` — DateField(null=True, blank=True) — seasonal applicability (e.g. heating Nov–Mar); null = always
- `applies_to` — DateField(null=True, blank=True)
- `min_party` — PositiveSmallInteger(null=True, blank=True) — e.g. extra-bed fee only for 5+ guests
- `max_party` — PositiveSmallInteger(null=True, blank=True)
- `sort_order` — int(default=0)
- `is_active` — BooleanField(default=True)
- `notes` — TextField(blank=True)

Constraints:
- `CheckConstraint(applies_from IS NULL OR applies_to IS NULL OR applies_from <= applies_to)`
- `CheckConstraint(min_party IS NULL OR max_party IS NULL OR min_party <= max_party)`

Index: `(property, is_active, sort_order)`.

#### Why property-scoped, not card-scoped

The product UX (`product-design/03-workflows.md` flow 13) renders extras inside the rate-card edit form. That's an *editing affordance*: the operator picks which property-level extras a given card "uses". The source of truth stays at property level because (a) cleaning fees don't vary card-to-card in practice, (b) seasonality is expressed via `applies_from`/`applies_to`, and (c) party-size variation is expressed via `min_party`/`max_party`. If a real per-card override need ever emerges, add a nullable `card` FK then — don't pre-empt.

#### Selection at quote time

- All `is_mandatory=True` Extras matching `(stay dates ∩ applies_from..applies_to, party ∈ [min_party..max_party])` are applied automatically.
- The pricing engine's `PricingEngine.quote(...)` accepts an `opt_in_extras=[<extra_id>, ...]` argument; only those non-mandatory Extras are added.
- Each applied Extra contributes a line to `Quote.breakdown.extras` with `{extra_id, name, kind, calc, amount, computed_amount}`. The snapshot persists on `Booking.pricing_snapshot`.

## Discounts

### `Discount(AuditedModel)`
Promo/code discounts and rate-card-level rules (early-bird, last-minute, length-of-stay, repeat-guest). One-off booking discounts go on `Booking.adjustment`, not here.
- `card` — FK RateCard CASCADE, null=True (null = property-wide, e.g. a promo code that's not tied to a single card)
- `property` — FK Property CASCADE (denorm for query simplicity when `card` is null; equals `card.plan.property` when card is set)
- `name` — CharField
- `code` — CharField(unique=True, null=True, blank=True)
- `rule_kind` — TextChoices (`LENGTH_OF_STAY`, `EARLY_BIRD`, `LAST_MINUTE`, `REPEAT_GUEST`, `PROMO_CODE`)
- `kind` — TextChoices (`PERCENT`, `FIXED`)
- `amount` — Decimal(12, 2)
- `min_nights` — PositiveSmallInteger(default=0)
- `threshold_days` — PositiveSmallInteger(null=True) — for early-bird / last-minute
- `valid_from`, `valid_to` — DateField
- `max_uses` — PositiveIntegerField(null=True, blank=True)
- `uses_count` — PositiveIntegerField(default=0) — incremented atomically on booking
- `is_active` — bool

Constraint: `CheckConstraint(card IS NOT NULL OR property IS NOT NULL)`.

## Change-over rules

### `ChangeOverRule(AuditedModel)`
Enforces which weekdays a booking can start. Replaces unused legacy `ChangeOverDays` lookup.
- `property` — FK Property CASCADE
- `weekday` — PositiveSmallInteger (0=Mon, 6=Sun)
- `effective_from`, `effective_to` — DateField (null=True for open-ended)
- `notes` — TextField(blank=True)

Many rows per property = the set of allowed check-in weekdays for that window. Zero rows = any day allowed. Engine uses these in `AvailabilityService.is_available()` and `BookingHold.clean()`.

## Pricing summary (signal-rebuilt cache)

### `VillaPricingSummary(TimestampedModel)`
Explicit, named cache for website min/max display. Replaces denormalised legacy `VillaWebsitePricing` and `VillaMapping`.
- `property` — FK Property CASCADE
- `currency` — FK Currency PROTECT
- `min_nightly`, `max_nightly` — Decimal(12, 2, null=True)
- `min_weekly`, `max_weekly` — Decimal(12, 2, null=True)
- `next_available_date` — DateField(null=True)
- `min_party`, `max_party` — PositiveSmallInteger
- `rebuilt_at` — DateTimeField

Constraint: `UniqueConstraint(property, currency)`.

Ownership:
- Rebuilt by a single service function `rebuild_summary(property, currency)` in `pricing.tasks`.
- `post_save`/`post_delete` signal on `RateRule` and `RatePlan` enqueues a debounced Celery task per `(property, currency)`.
- Nightly Celery beat task refreshes `next_available_date` (which depends on bookings/holds, not just rate rules).
- **No view/admin writes**. This is a cache; user-facing UIs read from it but never write.

## Services

### `pricing.services.PricingEngine`
Stateless. The public surface:

```python
@dataclass
class QuoteLine:
    date: date
    rule_id: int
    nightly: Decimal
    notes: str = ""

@dataclass
class AppliedExtra:
    extra_id: int
    name: str
    kind: str
    calc: str
    computed_amount: Decimal

@dataclass
class Quote:
    property_id: int
    currency_code: str
    party: int
    date_from: date
    date_to: date
    lines: list[QuoteLine]
    rate_subtotal: Decimal
    extras: list[AppliedExtra]
    extras_total: Decimal
    discount: Decimal
    commission: Decimal
    tax: Decimal
    total: Decimal
    net_to_owner: Decimal
    changeover_shifted_from: date | None = None
    is_projected: bool = False  # True when no real plan covered the stay and the quote was derived from a prior year — surfaces the "guide rate, inquire" marker
    breakdown: dict           # full snapshotable JSON (also carries is_projected + projection provenance)

class PricingEngine:
    @classmethod
    def quote(cls, *, property, date_from, date_to, party, currency,
              discount_code=None, opt_in_extras: list[int] | None = None,
              as_of=None) -> Quote: ...
```

Steps:
1. Resolve `RatePlan` for property + currency + date range.
1a. **Changeover auto-shift (GAP-007):** before pricing, nudge a non-conforming
   arrival forward to the next valid changeover day (legacy
   `ResService.cs:2028-2041`). The property's effective changeover day is the
   single source (`ChangeoverService` — `ChangeOverRule` window →
   `PropertySettings`/group chain; `any` = no shift). `date_from` advances to the
   next allowed weekday and `date_to` shifts by the **same delta** so the night
   count is preserved (legacy kept `date_to` fixed, silently shortening the stay —
   we don't). The original arrival is surfaced as `Quote.changeover_shifted_from`
   (`None` when no shift). An off-changeover arrival is **never rejected** — it is
   always shifted and surfaced; there is no override flag and no hard-reject gate.
2. Resolve the pricing context: `_load_real_context` returns the (plan, cards, rules) triple from a real plan covering the whole stay, or `None`. On `None` (and unless `allow_projection=False`), fall through to `RateProjectionService.project()`, which returns an equivalent in-memory triple synthesized from the anchor year with `Quote.is_projected=True`; if that is also `None`, raise `NoRateAvailable`. Because a real plan must span the whole stay, real always beats projected. Then for each night in range: walk all `RateCard`s in the (real or projected) plan in `(sort_order, pk)` order; within each card, filter `RateRule`s by `is_approved=True`. The **first card** with a rule covering both the night and the party wins — later cards never override it, however narrow their rules. Within-card duplicates are impossible in the DB (`raterule_no_overlap`); in-memory projected rules can collide after Feb-29 date mapping and resolve to the lowest `pk`. Validate the resulting card's `min_nights` / `max_nights` against the stay. Raise `NoRateAvailable` if no card matches; raise `MinNightsNotMet` if the matched card's length-of-stay constraints fail. (Changeover is handled entirely in step 1a — cards carry no changeover constraint.)
   - **No-coverage fallback (GAP-008):** if no rule covers a night at all
     (`NoCoverage`) and the plan sets `RatePlan.fallback_nightly`, the night is
     priced at that opt-in rate via a synthetic `QuoteLine` with
     `rule_id=None` / `card_id=None`. When `fallback_nightly is None` the night
     raises `NoRateAvailable` as before. The fallback never masks a party-bracket
     miss (`OutOfRange` still raises `PartyOutOfRange`). If *every* night is
     fallback there is no winning card, so the card `min_nights` / `max_nights`
     validation is skipped (legacy had no card concept on the
     `SettingNightlyPrice` path).
3. Build per-night `QuoteLine`s (carrying `card_id` and `rule_id` for traceability — both `None` on a fallback line).
4. Compute rate subtotal.
5. Apply mandatory `Extra`s whose date window intersects the stay and whose party-size window includes the party (calc methods: per-stay, per-night, per-person, per-person-per-night, percent-of-subtotal).
6. Apply caller-supplied opt-in `Extra`s (the `opt_in_extras` argument).
7. Apply `Discount` rules that match the winning card (`card_id`) or the property (when `card` is null) — auto-apply rule_kinds (LENGTH_OF_STAY, EARLY_BIRD, LAST_MINUTE) plus optional PROMO_CODE. `REPEAT_GUEST` is a recognised enum member but **not implemented in v1** (no repeat-guest detection exists yet); the engine excludes it at the queryset so it can never silently mis-apply (see GAP-009).
8. **Derive commission and tax `price_basis`-aware (BUG-009).** Read the resolved `RatePlan.price_basis` (authoritative — see "Which basis field" below). The rate is either the guest-facing gross or the owner net, and commission/tax are derived differently in each mode, with **mode-dependent bases**, mirroring legacy `RatesModel.Calculate()` (`ResSystem/NewResSystem.Core/Services/Properties/RatesModel.cs:112-252`). Let `base = rate_subtotal + extras − discounts`.
   - **GROSS** — the rate already includes tax and commission; **carve them out, never add on top**:
     - `tax = base × tax_rate/100` (tax base = the gross `base`)
     - `commission = (base − tax) × commission_pct/100` (commission base = gross − tax)
     - `total = base` (the guest pays the gross); `net_to_owner = base − tax − commission`
   - **NET** — the rate is the owner net; **gross up**:
     - `commission = base/(1 − commission_pct/100) − base` (commission base = net)
     - `tax = (base + commission)/(1 − tax_rate/100) − (base + commission)` (tax base = net + commission)
     - `total = base + commission + tax`; `net_to_owner = base`

   Legacy applied the mode maths per rate row (on the weekly/nightly figure), not to extras; the rebuild applies them to the combined `base` — revisit if extras must ever be tax-exempt (finance rewrite). The tax base and the commission base differ by mode (note the order: GROSS taxes the gross then commissions the post-tax remainder; NET commissions the net then taxes net+commission).
9. **Fixed vs percentage commission; exemption.** A *percentage* commission scales with its mode base as above. A *fixed* commission is the flat amount in **both** modes (legacy `CommissionAmount = Commission`). Tax is skipped entirely when `effective_tax_policy` reports exempt. The `effective_commission` / `effective_tax_policy` resolvers live in `03-finance-config.md`; `PropertyFinance` does **not** model NET/GROSS — basis lives on `RatePlan`, so the finance side only supplies pct / fixed / exempt and needs no new field. *(Implementation note: today's engine treats a **fixed** commission as an owner-payout concern and omits it from the guest-price line — a deliberate divergence from legacy that the finance rewrite must close or ratify; see BUG-009.)*
10. Snapshot full breakdown to `Quote.breakdown` (this is what `QuotationLine.pricing_snapshot` and `Booking.pricing_snapshot` persist). `total` is assembled per the plan's `price_basis` (step 8 — added-on-top for NET, identical to the gross rate for GROSS), but `net_to_owner = total - commission - tax` holds in **both** modes. The breakdown carries `total`, `commission`, `tax`, `is_projected`, `projection` (provenance, or `null`), and `net_to_owner` as explicit fields — owner-facing serializers read `net_to_owner` directly from the snapshot rather than recomputing. Legacy-loader snapshots (`BookingLoader` writes `{}`) and pre-this-contract snapshots fall back to subtracting client-side; new snapshots written by `PricingEngine.quote` always carry `net_to_owner`.

> **Which basis field is authoritative (BUG-009 ↔ GAP-035, resolved 2026-06-22).**
> The engine reads **`RatePlan.price_basis`** — basis is a per-plan property (a
> villa may run a GROSS public plan and a NET agent plan at once), so it resolves
> *with the plan*, not the property. `RatePlan.price_basis` is the **sole pricing
> authority**. `PropertySettings.prices_entered_as` /
> `GroupSettings.prices_entered_as` is **no longer a second basis field**: GAP-035
> demoted it to the **entry-time default** that pre-fills a *new* season's
> `price_basis` (`SeasonFormDialog`), nothing more. The one residual code path that
> still reads `prices_entered_as` for money is the Booking owner-statement
> serializer (`reservations/serializers/booking.py`); the BUG-009 finance rewrite
> closes that by reading `net_to_owner` from the snapshot (step 10) instead. Until
> the rewrite lands, `RatePlan.price_basis` is canonical for pricing.

#### Rate entry: net↔gross derivation (GAP-035)

Owners quote rates as either net or gross. The rate-band form lets staff type one
figure, pick the plan's `price_basis`, and shows the **derived counterpart** live
beside the input — owner net for a GROSS plan, guest price for a NET plan — so the
operator never hand-converts. The derivation uses the **same mode-aware math as
steps 8-9** (commission **+** tax, percentage grosses up by `÷(1−pct)`, fixed
commission flat both ways, tax skipped when exempt, `ROUND_HALF_EVEN`). It targets
the **corrected** engine: because the steps 8-9 carve-out/gross-up is itself
deferred (BUG-009 — today's engine still adds on top), the hint will match the
engine's quote *once BUG-009 lands*; until then it shows the figure the engine
*should* produce, which can differ from today's output once commission/tax are
non-zero. It is **derive-on-display only**:
the stored row is exactly the typed figure + `price_basis` — never the computed
side, which the engine's BUG-009 carve-out would otherwise re-derive and
double-count. Commission/tax inputs are `PropertyFinance.effective_commission()` /
`effective_tax_policy()` resolved property→group, surfaced read-only on the
**settings** endpoint (`commission`, `tax`, `prices_entered_as_effective`). The
helper is `frontend/src/lib/pricing/netGross.ts`; the form wiring is
`RateRuleFormDialog`. (Decision row: `10-decisions.md`, 2026-06-22.)

**Breakdown enrichment (2026-06 quote-builder rework).** The breakdown additionally carries plan/card metadata the quote builder renders on each result line — all from data already in memory at quote time, zero extra queries: `inclusion` (the winning plan's inclusion text, which also seeds `QuotationLine.inclusions` at line creation — legacy `ResService.cs:1241` parity), `changeover_day` (the effective day code, `null` when unconstrained), `min_nights`/`max_nights` (the winning card's bounds, `null` on an all-fallback stay), and `occupancy_pricing` (true when the winning card has >1 distinct party band, i.e. the price moves with party size).

**`PricingEngine.stay_length_bounds(property, date_from=…, date_to=…, currency=None)`** exposes the covering plan's aggregate card `(min_nights, max_nights)` without running a quote — used by the reservations-layer stay-option search (`POST /quotations:search-options`, see `06-availability.md`) to pick a changeover-block length before pricing. Returns `None` on the projection / no-plan path, in which case callers skip the clamp and the engine's own `MinNightsNotMet` stays the loud guard.

The engine raises typed exceptions (`NoRateAvailable`, `PartyOutOfRange`, `DiscountNotApplicable`, `MinNightsNotMet`, `ChangeoverViolation`) — the calling reservations code maps these to user-facing errors. `is_approved=False` rules are filtered before the resolver runs, so unapproved imports cannot leak into a quote. `pick_rule_for_night` returns a tagged result distinguishing `Picked` (rule matched), `OutOfRange` (rules cover the night but party doesn't match any bracket → `PartyOutOfRange`), and `NoCoverage` (no rule covers the night → `NoRateAvailable`).

#### Occupancy bracket: matched, not silently fallen-back

`PricingEngine.quote()` resolves the `RateRule` whose `(min_party, max_party)` interval contains the inquiry's party size, and raises `PartyOutOfRange` when no band matches. This is a behaviour change from the legacy quote path (`ResService.cs:ProcessQuotationItemAsync` + `RatesModel.Calculate()`, not the same-named search proc): when a party matched no occupancy band, legacy silently fell back to the **base weekly rate ÷ 7** (`ResService.cs:2117-2134`, `weeklyPrice += priceObj.WeeklyPrice / 7`) rather than surfacing the gap. See `09-departures.md` "Legacy correctness bugs explicitly fixed" #2. The legacy silent fallback is not preserved under any flag.

### `pricing.services.FxConverter`
```python
convert(amount: Decimal, from_ccy: Currency, to_ccy: Currency, as_of: date | None = None) -> Decimal
```
Picks the latest `FxRate` ≤ `as_of` (defaults to today). Used by website display only; bookings always price in the property's currency.

### `pricing.services.AvailabilityService`
Lives here (not reservations) because it needs change-over rules and is consumed by both quote-time and booking-time code. See 06-availability.md for full design.

## Future pricing models (not in MVP)

Two pricing shapes are recognised as out-of-scope for v1 but worth keeping the schema amenable to:

- **Per-person base rate (Kenya safari model).** The base nightly rate scales by occupant count rather than per stay. Distinct from per-person *fees* (already supported via `Extra.calc = FIXED_PER_PERSON` / `FIXED_PER_PERSON_PER_NIGHT`) — this is a per-person *base*. The Kenyan property mix historically used this model; European villas do not. When this lands, the cleanest extension is a `RateRule.calc_basis` enum (`PER_STAY` / `PER_NIGHT` / `PER_PERSON_PER_NIGHT`) defaulting to the current shape. Surfaced in `10-decisions.md` as deferred.
- **Minimum-occupancy with last-minute drop.** A villa quotes for a minimum party size (e.g. 6) at the standard rate, with last-minute (≤14 days out) bookings allowed below the minimum at the same total. Already partially expressible via `RateRule.min_party` + a manual override, but no automatic "drop-the-minimum on close-in dates" logic is built.

Neither shape changes the existing model in a breaking way; both are documented here so they don't get reinvented as bespoke special-cases when the time comes.

## Why this replaces sp_getQuotationData

The legacy 500+ LOC stored procedure mixed rate lookup, occupancy bands, tax, commission, discount, availability check, and currency conversion in one untestable blob. Pulling each concern into its own model and the orchestration into a service gives:

- Unit-testable engine (pass lists, not DB fixtures).
- Composable extras (add a new fee type by adding an `Extra` row, not editing SQL).
- Explicit pricing snapshot persisted on Quotation and Booking — full traceability of how a price was derived.
- Multi-currency support without code duplication.
- A single place to add caching if needed (rate rule lookup is the hot path).
