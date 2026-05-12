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
- `RateCard` — the operator's "rate card". The unit of editing in the admin UI: has name, min/max nights, changeover restriction, and is what `Discount` rules attach to.
- `RateRule` — the price row. One per (date sub-range × party-size band) inside a card. Occupancy bands are sibling rules sharing date range with different `(min_party, max_party)`.

This three-level split honours the operator mental model (see `product-design/03-workflows.md` flow 13) without re-introducing the legacy `VillaSeasonDate` table — date ranges live on `RateRule`. Production data confirms this is the right shape: 96% of legacy seasons had a single date range; only 3% of rate rows had occupancy bands, so a separate band table is unjustified.

**Lifecycle.** Every rate model is `AuditedModel` only. Retiring a plan/card/rule is done by toggling `is_active=False` (already on `RatePlan` / `RateCard`) or by setting `effective_to` to a past date (`RateRule.date_from`/`date_to` already bound applicability). Historical bookings keep their pricing via `Booking.pricing_snapshot`, so a previously-active rate that is now switched off does not retroactively change any booking's recorded price. Hard delete is permitted for "rule entered in error" cases (no FK from `Booking` to `RateRule` — bookings reference only their snapshot).

### `RatePlan(AuditedModel)`
Groups a set of cards; replaces legacy `VillaSeason` as the grouping container. Carries no prices.
- `property` — FK properties.Property PROTECT
- `name` — CharField (e.g. "Summer 2026", "2026 Agent Net")
- `currency` — FK Currency PROTECT
- `price_basis` — TextChoices (`GROSS`, `NET`) — gross is customer-facing, net is agent
- `effective_from` — DateField
- `effective_to` — DateField(null=True, blank=True) — open-ended
- `is_active` — bool
- `notes` — TextField(blank=True)
- `inclusion` — TextField(blank=True) — free-text "what's included" copy (e.g. chef, daily housekeeping)

### `RateCard(AuditedModel)`
The operator-facing rate-card unit; the level at which length-of-stay rules, discounts, and changeover restrictions attach. Has no prices of its own — those live on child `RateRule`s.
- `plan` — FK RatePlan CASCADE
- `name` — CharField (e.g. "Peak weeks", "Shoulder")
- `description` — TextField(blank=True)
- `min_nights` — PositiveSmallInteger(default=1)
- `max_nights` — PositiveSmallInteger(null=True, blank=True)
- `changeover_weekday` — PositiveSmallInteger(null=True, blank=True) — overrides property `ChangeOverRule` when set; null means defer to property rule
- `sort_order` — int(default=0)
- `is_active` — bool(default=True)
- `notes` — TextField(blank=True)

Index: `(plan, sort_order)`.

### `RateRule(AuditedModel)`
The fundamental price row. Replaces `VillaSeasonRate` × `VillaOccupencyPrice` × `VillaSeasonDate`.
- `card` — FK RateCard CASCADE
- `date_from` — DateField
- `date_to` — DateField
- `min_party` — PositiveSmallInteger(default=1)
- `max_party` — PositiveSmallInteger
- `priority` — PositiveSmallInteger(default=0) — higher wins on overlap
- `nightly` — Decimal(12, 2, null=True, blank=True)
- `weekly` — Decimal(12, 2, null=True, blank=True)
- `is_poa` — BooleanField(default=False)
- `is_locked` — BooleanField(default=False) — preserves the rule against bulk recompute / re-import. Bulk services (any future "regenerate rates for season X" admin action, CSV re-import, FX-driven mass adjustment) skip locked rules. Individual edits via the admin / API are unaffected and clear the lock implicitly only when the operator confirms in the UI. Replaces the legacy `IsManualUpdate` flag from `workflows/04-pricing/rates.md`.
- `is_approved` — BooleanField(default=True) — gates engine visibility. Staff-created rules default to `True`; bulk-imported rules land as `False` and require an explicit approval pass before `PricingEngine.quote()` will consider them. Replaces the legacy `IsApprove` workflow step.
- `notes` — TextField(blank=True)

Constraints (Postgres):
- `CheckConstraint(date_from <= date_to)`
- `CheckConstraint(min_party <= max_party)`
- `CheckConstraint(nightly IS NOT NULL OR weekly IS NOT NULL OR is_poa)` — must have a price or be POA
- `EXCLUDE USING gist (card_id WITH =, daterange(date_from, date_to, '[]') WITH &&, int4range(min_party, max_party, '[]') WITH &&, priority WITH =)` — prevents accidental same-tier overlap within a card; different priorities are allowed and disambiguated by the engine. Cross-card overlap is allowed (and resolved by `priority` at quote time, walking through all cards in the plan).

Index: `(card, date_from, date_to)`, `(card, priority DESC)`.

#### Occupancy bands
A card with multiple party-size bands is represented as **multiple `RateRule` rows** sharing a `card_id` and date range, with disjoint `(min_party, max_party)` intervals. The `EXCLUDE` constraint permits this because party range is part of the exclusion tuple. No separate band table.

#### Disjoint date ranges within a card
A card whose price applies to multiple non-contiguous date ranges is represented as multiple `RateRule` rows sharing `card_id` and party range, with disjoint date intervals.

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
    breakdown: dict           # full snapshotable JSON

class PricingEngine:
    @classmethod
    def quote(cls, *, property, date_from, date_to, party, currency,
              discount_code=None, opt_in_extras: list[int] | None = None,
              as_of=None) -> Quote: ...
```

Steps:
1. Resolve `RatePlan` for property + currency + date range.
2. For each night in range: walk all `RateCard`s in the plan; within each card, filter `RateRule`s by `is_approved=True`, then pick the highest-priority rule matching date + party. **Tie-break:** equal `priority` is resolved by the most-specific date range (narrowest `date_to - date_from`), then by `id` descending. The card whose rule has the highest priority wins overall (cross-card ties broken by `card.sort_order`). Validate the resulting card's `min_nights` / `max_nights` / `changeover_weekday` against the stay. Raise `NoRateAvailable` if no card matches; raise `MinNightsNotMet` / `ChangeoverViolation` if the matched card's constraints fail.
3. Build per-night `QuoteLine`s (carrying `card_id` and `rule_id` for traceability).
4. Compute rate subtotal.
5. Apply mandatory `Extra`s whose date window intersects the stay and whose party-size window includes the party (calc methods: per-stay, per-night, per-person, per-person-per-night, percent-of-subtotal).
6. Apply caller-supplied opt-in `Extra`s (the `opt_in_extras` argument).
7. Apply `Discount` rules that match the winning card (`card_id`) or the property (when `card` is null) — auto-apply rule_kinds (LENGTH_OF_STAY, EARLY_BIRD, LAST_MINUTE, REPEAT_GUEST) plus optional PROMO_CODE.
8. Apply commission from `property.finance.effective_commission()` (the resolver in `03-finance-config.md`).
9. Apply tax last from `property.finance.effective_tax_policy()` — tax base is rate subtotal + extras − discounts.
10. Snapshot full breakdown to `Quote.breakdown` (this is what `QuotationLine.pricing_snapshot` and `Booking.pricing_snapshot` persist).

The engine raises typed exceptions (`NoRateAvailable`, `PartyOutOfRange`, `DiscountNotApplicable`, `MinNightsNotMet`, `ChangeoverViolation`) — the calling reservations code maps these to user-facing errors. `is_approved=False` rules are filtered before the resolver runs, so unapproved imports cannot leak into a quote.

### `pricing.services.FxConverter`
```python
convert(amount: Decimal, from_ccy: Currency, to_ccy: Currency, as_of: date | None = None) -> Decimal
```
Picks the latest `FxRate` ≤ `as_of` (defaults to today). Used by website display only; bookings always price in the property's currency.

### `pricing.services.AvailabilityService`
Lives here (not reservations) because it needs change-over rules and is consumed by both quote-time and booking-time code. See 06-availability.md for full design.

## Why this replaces sp_getQuotationData

The legacy 500+ LOC stored procedure mixed rate lookup, occupancy bands, tax, commission, discount, availability check, and currency conversion in one untestable blob. Pulling each concern into its own model and the orchestration into a service gives:

- Unit-testable engine (pass lists, not DB fixtures).
- Composable extras (add a new fee type by adding an `Extra` row, not editing SQL).
- Explicit pricing snapshot persisted on Quotation and Booking — full traceability of how a price was derived.
- Multi-currency support without code duplication.
- A single place to add caching if needed (rate rule lookup is the hot path).
