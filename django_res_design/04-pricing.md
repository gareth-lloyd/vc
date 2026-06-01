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

**Why seasons stay per-property.** The mockup-demo (2026-05-29) explored standardising seasons across the portfolio (VC-defined peak/shoulder/low) and splitting Season→Inclusions→Rates into separate layers. We deliberately **keep the per-property shape**. The operator's driver for "how many seasons a villa has" is **service inclusions**: a villa needs multiple `RatePlan`s only when what's included changes across the year (e.g. high season bundles a private chef; low season doesn't). Where inclusions are constant year-round, one plan suffices regardless of rate variation — high/mid/low price differences live in sibling `RateCard`s within a plan. `RatePlan.inclusion` stays the descriptive field; there is **no** first-class `Inclusion` entity and **no** portfolio-wide standard-season catalogue (it would fight the 96%-single-range finding for a reporting convenience with no named consumer yet). VC-standard reporting *labels* (peak/shoulder/low) are wanted but their placement — most likely on `RatePlan`, not `RateCard` — is an open follow-up (`10-decisions.md`). See `10-decisions.md` "Seasons stay per-property; inclusions drive how many a villa has".

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
- `is_provisional` — BooleanField(default=False) — a **carried-over guide rate** awaiting owner confirmation for the new year. Distinct from `is_approved`: provisional rules **are** quotable (the engine uses them), but the resulting quote is flagged so the generator/email render a "rates carried over — inquire for accurate rate" marker. Cleared when staff/owner confirm the real rate. See "Carryover & provisional rates" below.
- `carried_over_from` — FK self SET_NULL, null=True, blank=True — the source rule a provisional clone was rolled forward from; for traceability and so a confirm action can compare against last year. Null for hand-entered rules.
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

## Carryover & provisional rates

At this time of year clients inquire for *next* year, but only ~10% of next-year rates are
confirmed — so quoting next year is slow manual work, and owners are slow to return rates.
Legacy handled this by hand: rename last year's season, shift its dates, copy each rate over.
The rebuild **automates the roll-forward** and makes the provisional state first-class. This
is an M1 feature (`11-milestones.md`) and the stated highest-value time-saver
(`10-decisions.md` "Carryover / provisional rates").

### `pricing.services.RateCarryoverService`

```python
class RateCarryoverService:
    @classmethod
    def roll_forward(cls, plan: RatePlan, *, to_year: int, date_map=shift_to_changeover_weekday) -> RatePlan:
        """Clone `plan` (cards + rules) into `to_year`. Cloned rules are marked
        is_provisional=True and carried_over_from=<source rule>. Idempotent per
        (property, to_year): re-running updates the existing provisional set, never
        duplicates, and never touches rules an owner has already confirmed."""
```

- Default behaviour is to roll **every** active `RatePlan` forward into the next year (a
  Celery beat task `pricing.tasks.carry_over_rates`, run at season boundary), so the quoting
  team always has a guide rate to quote against. Manual per-plan invocation is also exposed in
  the admin. This **supersedes the manual `:COPY`** as the default; manual copy stays for
  ad-hoc cloning (`workflows/04-pricing/seasons.md`).
- **Confirming real rates** clears `is_provisional` (and may adjust the figure). Once cleared,
  the rule is an official rate and the carryover task leaves it alone on subsequent runs.

#### Date mapping — `date_map` *(open follow-up)*

When a rule rolls forward, its `date_from`/`date_to` must move to the new year. There are two
candidate rules and the source conversation (2026-05-29) does **not** definitively settle
which the business wants:

- `shift_to_changeover_weekday` (default) — preserve the changeover weekday, so a Saturday-to-Saturday week stays Saturday-to-Saturday in the new year (dates shift by 1–2 days). Matches how villas with a `ChangeOverRule` actually let.
- `keep_calendar_date` — keep the same calendar dates, just relabel the year.

The service takes `date_map` as a swappable function defaulting to the weekday-aligned mapping;
the choice is flagged for confirmation against Bryony's listing Loom before it is hard-coded
(`10-decisions.md` open follow-up "Carryover date-mapping rule"). Do not bake the rule into the
clone logic — keep it in the injected function.

### Engine behaviour for provisional rules

`PricingEngine.quote()` treats `is_provisional` rules as fully quotable (unlike
`is_approved=False`, which are filtered out before the resolver). When **any** rule
contributing to a quote is provisional, the returned `Quote` carries `is_provisional=True` and
`Quote.breakdown["is_provisional"] = True`, so the quote generator and the outbound quotation
email render the "2027 rates carried over — guide rate, inquire for accurate rate" marker. The
flag is also persisted into `QuotationLine.pricing_snapshot` / `Booking.pricing_snapshot` so a
later reader can see the quote was built on provisional rates.

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
    is_provisional: bool = False  # True if any contributing RateRule.is_provisional — surfaces the "guide rate, inquire" marker
    breakdown: dict           # full snapshotable JSON (also carries is_provisional)

class PricingEngine:
    @classmethod
    def quote(cls, *, property, date_from, date_to, party, currency,
              discount_code=None, opt_in_extras: list[int] | None = None,
              as_of=None) -> Quote: ...
```

Steps:
1. Resolve `RatePlan` for property + currency + date range.
1a. **Changeover auto-shift (GAP-007):** before pricing, nudge a non-conforming
   arrival forward to the next valid changeover weekday (legacy
   `ResService.cs:2028-2041`). Allowed-weekday precedence: the active cards'
   `changeover_weekday` when they agree on a single day; otherwise the property's
   effective changeover day (`ChangeoverService` — `ChangeOverRule` window →
   `PropertySettings`/group chain; `any` = no shift). `date_from` advances to the
   next allowed weekday and `date_to` shifts by the **same delta** so the night
   count is preserved (legacy kept `date_to` fixed, silently shortening the stay —
   we don't). The original arrival is surfaced as `Quote.changeover_shifted_from`
   (`None` when no shift). A winning card that still demands a weekday the
   alignment couldn't satisfy raises `ChangeoverViolation` as a genuine-conflict
   backstop (step 2).
2. For each night in range: walk all `RateCard`s in the plan; within each card, filter `RateRule`s by `is_approved=True` (provisional rules pass this filter — `is_provisional` does not hide a rule, it only flags the quote), then pick the highest-priority rule matching date + party. If any picked rule is `is_provisional`, set `Quote.is_provisional = True`. **Tie-break:** equal `priority` is resolved by the most-specific date range (narrowest `date_to - date_from`), then by `id` descending. The card whose rule has the highest priority wins overall (cross-card ties broken by `card.sort_order`). Validate the resulting card's `min_nights` / `max_nights` / `changeover_weekday` against the stay. Raise `NoRateAvailable` if no card matches; raise `MinNightsNotMet` / `ChangeoverViolation` if the matched card's constraints fail.
   - **No-coverage fallback (GAP-008):** if no rule covers a night at all
     (`NoCoverage`) and the plan sets `RatePlan.fallback_nightly`, the night is
     priced at that opt-in rate via a synthetic `QuoteLine` with
     `rule_id=None` / `card_id=None`. When `fallback_nightly is None` the night
     raises `NoRateAvailable` as before. The fallback never masks a party-bracket
     miss (`OutOfRange` still raises `PartyOutOfRange`). If *every* night is
     fallback there is no winning card, so the card `min_nights` / `max_nights` /
     `changeover_weekday` validation is skipped (legacy had no card concept on
     the `SettingNightlyPrice` path).
3. Build per-night `QuoteLine`s (carrying `card_id` and `rule_id` for traceability — both `None` on a fallback line).
4. Compute rate subtotal.
5. Apply mandatory `Extra`s whose date window intersects the stay and whose party-size window includes the party (calc methods: per-stay, per-night, per-person, per-person-per-night, percent-of-subtotal).
6. Apply caller-supplied opt-in `Extra`s (the `opt_in_extras` argument).
7. Apply `Discount` rules that match the winning card (`card_id`) or the property (when `card` is null) — auto-apply rule_kinds (LENGTH_OF_STAY, EARLY_BIRD, LAST_MINUTE) plus optional PROMO_CODE. `REPEAT_GUEST` is a recognised enum member but **not implemented in v1** (no repeat-guest detection exists yet); the engine excludes it at the queryset so it can never silently mis-apply (see GAP-009).
8. Apply commission from `property.finance.effective_commission()` (the resolver in `03-finance-config.md`).
9. Apply tax last from `property.finance.effective_tax_policy()` — tax base is rate subtotal + extras − discounts.
10. Snapshot full breakdown to `Quote.breakdown` (this is what `QuotationLine.pricing_snapshot` and `Booking.pricing_snapshot` persist). The breakdown carries `total`, `commission`, `tax`, `is_provisional`, and `net_to_owner = total - commission - tax` as explicit fields — owner-facing serializers read `net_to_owner` directly from the snapshot rather than recomputing. Legacy-loader snapshots (`BookingLoader` writes `{}`) and pre-this-contract snapshots fall back to subtracting client-side; new snapshots written by `PricingEngine.quote` always carry `net_to_owner`.

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
