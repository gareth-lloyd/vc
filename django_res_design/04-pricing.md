# 04 — Pricing

The pricing app is a pure library: given a property, dates, party size, and currency, return a Quote. It has no knowledge of bookings, enquiries, or payments — those import from here.

## File layout

```
pricing/
├── enums.py
├── models/
│   ├── __init__.py
│   ├── currency.py     # Currency, FxRate
│   ├── rate.py         # RatePlan, RateRule
│   ├── surcharge.py    # Surcharge, Discount
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

### `RatePlan(SoftDeleteModel)`
Groups a set of rules; replaces legacy `VillaSeason` as the grouping container.
- `property` — FK properties.Property PROTECT
- `name` — CharField (e.g. "2026 Standard", "2026 Agent Net")
- `currency` — FK Currency PROTECT
- `price_basis` — TextChoices (`GROSS`, `NET`) — gross is customer-facing, net is agent
- `effective_from` — DateField
- `effective_to` — DateField(null=True, blank=True) — open-ended
- `is_active` — bool
- `notes` — TextField(blank=True)

### `RateRule(SoftDeleteModel)`
The fundamental rate unit. Replaces `VillaSeasonRate` × `VillaOccupencyPrice` × `VillaSeasonDate`.
- `plan` — FK RatePlan CASCADE
- `date_from` — DateField
- `date_to` — DateField
- `min_party` — PositiveSmallInteger(default=1)
- `max_party` — PositiveSmallInteger
- `priority` — PositiveSmallInteger(default=0) — higher wins on overlap
- `nightly` — Decimal(12, 2, null=True, blank=True)
- `weekly` — Decimal(12, 2, null=True, blank=True)
- `min_nights` — PositiveSmallInteger(default=1)
- `is_poa` — BooleanField(default=False)
- `notes` — TextField(blank=True)

Constraints (Postgres):
- `CheckConstraint(date_from <= date_to)`
- `CheckConstraint(min_party <= max_party)`
- `CheckConstraint(nightly IS NOT NULL OR weekly IS NOT NULL OR is_poa)` — must have a price or be POA
- `EXCLUDE USING gist (plan_id WITH =, daterange(date_from, date_to, '[]') WITH &&, int4range(min_party, max_party, '[]') WITH &&, priority WITH =)` — prevents accidental same-tier overlap; different priorities are allowed and disambiguated by the engine.

Index: `(plan, date_from, date_to)`, `(plan, priority DESC)`.

## Surcharges & discounts

### `Surcharge(SoftDeleteModel)`
Composable rules. Replaces tax/commission/discount fields-on-rate from legacy.
- `plan` — FK RatePlan CASCADE
- `kind` — TextChoices (`TAX`, `COMMISSION`, `CLEANING`, `SERVICE_FEE`, `RESORT_FEE`)
- `calc` — TextChoices (`PERCENT`, `FIXED_PER_NIGHT`, `FIXED_PER_STAY`, `FIXED_PER_PERSON_PER_NIGHT`)
- `amount` — Decimal(12, 4)
- `applies_to` — TextChoices (`SUBTOTAL`, `NIGHTLY`, `NET`) — what base the percent operates on
- `is_tax_exempt_eligible` — bool (this surcharge can be skipped if booking is tax-exempt)
- `effective_from`, `effective_to` — DateField (null=True for open-ended)
- `notes` — TextField(blank=True)

### `Discount(SoftDeleteModel)`
Promo/code discounts. One-off booking discounts go on `Booking.adjustment`, not here.
- `plan` — FK RatePlan CASCADE, null=True (null = applies to all of a property's plans)
- `property` — FK Property CASCADE (denorm for query simplicity if `plan` is null)
- `name` — CharField
- `code` — CharField(unique=True, null=True, blank=True)
- `kind` — TextChoices (`PERCENT`, `FIXED`)
- `amount` — Decimal(12, 2)
- `min_nights` — PositiveSmallInteger(default=0)
- `valid_from`, `valid_to` — DateField
- `max_uses` — PositiveIntegerField(null=True, blank=True)
- `uses_count` — PositiveIntegerField(default=0) — incremented atomically on booking
- `is_active` — bool

## Change-over rules

### `ChangeOverRule(SoftDeleteModel)`
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
class Quote:
    property_id: int
    currency_code: str
    party: int
    date_from: date
    date_to: date
    lines: list[QuoteLine]
    subtotal: Decimal
    surcharges: list[dict]    # [{kind, amount, calc, ...}]
    discount: Decimal
    total: Decimal
    breakdown: dict           # full snapshotable JSON

class PricingEngine:
    @classmethod
    def quote(cls, *, property, date_from, date_to, party, currency,
              discount_code=None, as_of=None) -> Quote: ...
```

Steps:
1. Resolve `RatePlan` for property + currency + date range.
2. For each night in range: pick highest-priority `RateRule` matching date + party. Raise `NoRateAvailable` if none.
3. Build per-night `QuoteLine`s.
4. Compute subtotal.
5. Apply `Surcharge`s in deterministic order (commission → cleaning → tax last on subtotal).
6. Apply optional `Discount` (code or auto-apply for min_nights).
7. Snapshot full breakdown to `Quote.breakdown` (this is what `QuotationLine.pricing_snapshot` and `Booking.pricing_snapshot` persist).

The engine raises typed exceptions (`NoRateAvailable`, `PartyOutOfRange`, `DiscountNotApplicable`) — the calling reservations code maps these to user-facing errors.

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
- Composable surcharges (add a new fee type by adding a row, not editing SQL).
- Explicit pricing snapshot persisted on Quotation and Booking — full traceability of how a price was derived.
- Multi-currency support without code duplication.
- A single place to add caching if needed (rate rule lookup is the hot path).
