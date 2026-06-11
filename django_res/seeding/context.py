"""Per-run state for the seed_dev command.

`SeedContext` is the single mutable bag stages read and write. Shared
collections (currencies, properties, guest pool, terms) live here so a
later stage can lean on rows an earlier stage built without round-tripping
through the DB.

`ProfileKnobs` holds the per-profile dials — fractions of cohorts, range
ints, etc. New stages add new dial fields here and set their values in
`_PROFILES` below.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any


def utc_today() -> date:
    """Today as a UTC calendar date — the anchor for all seeded date logic.

    Both dashboards compute "today" in UTC (settings TIME_ZONE is UTC, and the
    SPA uses `toISOString()`), so the seeder must too: a server-local
    `date.today()` puts today-anchored stays on the wrong calendar day for
    part of every day on any non-UTC machine.
    """
    return datetime.now(UTC).date()


# Rows per stage for each scale preset. Booking budgets are deliberately
# generous for the non-happy profiles: the `bookings` stage spreads them
# across density tiers (a few packed villas, several busy, many light, some
# empty) so default calendars read as realistically dense rather than near
# empty. `--bookings` still overrides the total exactly. `dashboard` is the
# multiplier the dashboard_activity stage applies to its guaranteed cohorts
# (arrivals/departures today, NEW enquiries, awaiting-balance stays).
_SCALES: dict[str, dict[str, int]] = {
    "small": {"properties": 5, "users": 4, "bookings": 30, "dashboard": 1},
    "medium": {"properties": 20, "users": 8, "bookings": 110, "dashboard": 2},
    "large": {"properties": 60, "users": 15, "bookings": 400, "dashboard": 3},
}


class Profile(StrEnum):
    HAPPY = "happy"
    MIXED = "mixed"
    CHAOS = "chaos"


@dataclass(frozen=True)
class ProfileKnobs:
    """Per-profile dials. Fractions are 0.0-1.0 of their cohort."""

    name: str
    pct_pre_approval_property: float = 0.0
    pct_owner_contact: float = 0.8
    pct_property_draft: float = 0.0
    pct_property_archived: float = 0.0
    # Of "quotation-only" attempts that never become bookings:
    pct_extra_quotation_per_booking: float = 0.0
    # Of bookings: extra non-happy lifecycle endings
    pct_booking_expires: float = 0.0
    pct_booking_pre_approval_declines: float = 0.0
    pct_booking_cancel_post_deposit: float = 0.0
    # Tier 2:
    pct_concierge: float = 0.0
    pct_refund_of_cancelled: float = 0.0
    pct_preference: float = 0.0
    # Enquiry-only paths (no quotation at all):
    pct_enquiry_lost_only: float = 0.0
    pct_enquiry_contacted_only: float = 0.0
    repeat_guest_pool_size: int = 0
    # Spread of booking date_from around today (±N days). 0 = legacy
    # (always near today). Larger = wider arrival calendar.
    booking_date_spread_days: int = 0
    # ---- v2 dials (new stages) ----
    # When True, run the one-shot system_setup stage (multi-currency, FxRates,
    # SMTP/templates, multiple TermsVersions). Always on outside `happy`.
    do_system_setup: bool = False
    # Number of distinct PropertyGroups created up-front to be assigned to
    # properties. 0 falls back to legacy 1-to-1 group-per-property.
    n_property_groups: int = 0
    # Inclusive room count range per property; (0, 0) disables.
    rooms_per_property: tuple[int, int] = (0, 0)
    # Inclusive feature count range per property.
    features_per_property: tuple[int, int] = (0, 0)
    # Inclusive extra gallery-image count range per property (beyond the
    # hero the PropertyFactory already creates).
    images_per_property: tuple[int, int] = (0, 0)
    # Inclusive nearby-place count range per property.
    nearby_per_property: tuple[int, int] = (0, 0)
    # Extra PropertyContactAssignments per property (in addition to the
    # optional Owner contact PropertyFactory already wires).
    pct_per_property: tuple[int, int] = (0, 0)
    # Number of Collections to create.
    n_collections: int = 0
    # Fraction of bookings/enquiries that pick up a note.
    pct_notes: float = 0.0
    # SyncRuns per provider, plus average records / issues per run.
    runs_per_channel: int = 0
    # Fraction of payments that get a WebhookDelivery row.
    pct_webhooks: float = 0.0
    # Fraction of (active) properties that get any operator-editable
    # availability block (owner_block / maintenance / manual). Keep low so
    # most calendars stay generally bookable.
    pct_properties_with_blocks: float = 0.0
    # Inclusive count range of blocks placed on each chosen property.
    blocks_per_property: tuple[int, int] = (0, 0)
    # Inclusive day-length range of each placed block.
    block_length_days: tuple[int, int] = (0, 0)
    # When True, the `bookings` stage spreads its budget across density tiers
    # (packed / busy / light / empty villas) and lays stays across the full
    # date window instead of a flat round-robin, so calendars read as densely
    # but realistically varied. happy stays False (legacy round-robin).
    dense_calendar: bool = False
    # Per-property check-out/check-in clock times as "HH:MM" strings, written
    # onto PropertySettings so back-to-back stays render an AM/PM changeover
    # day on the availability calendar. (None, None) leaves the times null
    # (happy), so no changeover split is produced.
    changeover_times: tuple[str | None, str | None] = (None, None)
    # Weighted (PrefilledChangeOverDay value, weight) distribution used to
    # assign each villa a changeover day; villas drawing a specific day (not
    # "any") also get the minimum-stay floor below. Mirrors the legacy prod
    # snapshot (88% explicit, Saturday-heavy). Empty tuple disables (happy).
    changeover_day_weights: tuple[tuple[str, float], ...] = ()
    # Minimum stay (nights) written to RateCard.min_nights (engine-enforced)
    # and PropertySettings.min_nights_rental (legacy-semantics field) on
    # villas with a specific changeover day. Legacy resolves to 7 virtually
    # everywhere.
    constrained_min_nights: int = 7
    # When True, villas price like the legacy book: per-currency log-normal
    # price levels, Low/Mid/Peak seasonal cards, near-universal percentage
    # commission, and the fractions below. False keeps the legacy factory
    # shape (one card, one flat 250/400/650 rule).
    realistic_pricing: bool = False
    # Fraction of villas with a second RatePlan in another currency (legacy:
    # ~13% of villas price in 2+ currencies).
    pct_second_currency: float = 0.0
    # Fraction of villas whose cards use occupancy-band sibling rules
    # (legacy: ~4% of rates; bumped a little so small runs reliably get one).
    pct_occupancy_bands: float = 0.0
    # Fraction of villas that get a Discount row. 1.0 = legacy seeder shape
    # (every villa); discounts are effectively dead in the legacy book.
    pct_discount: float = 1.0


_PROFILES: dict[Profile, ProfileKnobs] = {
    Profile.HAPPY: ProfileKnobs(name="happy"),
    Profile.MIXED: ProfileKnobs(
        name="mixed",
        pct_pre_approval_property=0.15,
        pct_owner_contact=0.70,
        pct_property_draft=0.05,
        pct_property_archived=0.05,
        pct_extra_quotation_per_booking=0.25,
        pct_booking_expires=0.06,
        pct_booking_pre_approval_declines=0.40,
        pct_booking_cancel_post_deposit=0.15,
        pct_concierge=0.30,
        # Refund the majority of refundable cancellations so every refund
        # state (REJECTED / APPROVED / FAILED / SUCCEEDED) is reachable in
        # any decent-sized run.
        pct_refund_of_cancelled=0.80,
        pct_preference=0.25,
        pct_enquiry_lost_only=0.10,
        pct_enquiry_contacted_only=0.10,
        repeat_guest_pool_size=4,
        booking_date_spread_days=365,
        # v2 dials:
        do_system_setup=True,
        n_property_groups=3,
        rooms_per_property=(4, 8),
        features_per_property=(5, 15),
        images_per_property=(4, 12),
        nearby_per_property=(3, 8),
        pct_per_property=(1, 3),
        n_collections=4,
        pct_notes=0.40,
        runs_per_channel=3,
        pct_webhooks=0.60,
        # Blocks land on a bit over half the active villas (a mix, not every
        # calendar), 1-3 each, so owner_block / maintenance / manual show up
        # densely without smothering bookable availability.
        pct_properties_with_blocks=0.55,
        blocks_per_property=(1, 3),
        block_length_days=(2, 5),
        dense_calendar=True,
        changeover_times=("10:00", "16:00"),
        changeover_day_weights=(
            ("sat", 0.72),
            ("mon", 0.10),
            ("sun", 0.04),
            ("fri", 0.02),
            ("any", 0.12),
        ),
        realistic_pricing=True,
        pct_second_currency=0.13,
        pct_occupancy_bands=0.12,
        pct_discount=0.15,
    ),
    Profile.CHAOS: ProfileKnobs(
        name="chaos",
        pct_pre_approval_property=0.30,
        pct_owner_contact=0.50,
        pct_property_draft=0.08,
        pct_property_archived=0.08,
        pct_extra_quotation_per_booking=0.50,
        pct_booking_expires=0.12,
        pct_booking_pre_approval_declines=0.50,
        pct_booking_cancel_post_deposit=0.10,
        pct_concierge=0.50,
        pct_refund_of_cancelled=0.60,
        pct_preference=0.45,
        pct_enquiry_lost_only=0.20,
        pct_enquiry_contacted_only=0.15,
        repeat_guest_pool_size=8,
        booking_date_spread_days=365,
        # v2 dials (cranked):
        do_system_setup=True,
        n_property_groups=3,
        rooms_per_property=(3, 10),
        features_per_property=(8, 20),
        images_per_property=(6, 16),
        nearby_per_property=(5, 12),
        pct_per_property=(2, 4),
        n_collections=5,
        pct_notes=0.60,
        runs_per_channel=5,
        pct_webhooks=0.80,
        pct_properties_with_blocks=0.55,
        blocks_per_property=(1, 4),
        block_length_days=(2, 7),
        dense_calendar=True,
        changeover_times=("10:00", "16:00"),
        changeover_day_weights=(
            ("sat", 0.72),
            ("mon", 0.10),
            ("sun", 0.04),
            ("fri", 0.02),
            ("any", 0.12),
        ),
        realistic_pricing=True,
        pct_second_currency=0.13,
        pct_occupancy_bands=0.12,
        pct_discount=0.15,
    ),
}


@dataclass
class SeedContext:
    """Mutable per-run state. Stages read/write the shared collections."""

    rng: random.Random
    knobs: ProfileKnobs
    n_properties: int
    n_bookings: int
    n_users: int
    # Multiplier for the dashboard_activity cohorts (set from the scale
    # preset). 0 disables the stage (`--no-dashboard-activity`).
    dashboard_factor: int = 1
    today: date = field(default_factory=utc_today)
    # Shared collections, populated as stages run.
    currencies: dict[str, Any] = field(default_factory=dict)
    properties: list[Any] = field(default_factory=list)
    # property pk -> manifest villa slug, when a property was seeded from the
    # villa manifest. Lets the `gallery` stage load non-HERO images from the
    # same villa the `properties` stage assigned (and which the factory used
    # for the HERO), keeping each property's image set coherent.
    property_villa: dict[int, str] = field(default_factory=dict)
    groups: list[Any] = field(default_factory=list)
    guest_pool: list[Any] = field(default_factory=list)
    terms: list[Any] = field(default_factory=list)
    # Run-local pks so later stages (notes, webhooks) can scope to rows this
    # run created instead of touching every row in the table — additive
    # reruns must not silently mutate prior-run or fixture data.
    booking_pks: list[int] = field(default_factory=list)
    enquiry_pks: list[int] = field(default_factory=list)
    # property pk -> (required changeover weekday per date.weekday() or None,
    # min nights). Written by the `properties` stage from the rules it just
    # seeded; booking-creating stages conform stays through it (see
    # `conforming_stay`) instead of re-resolving settings from the DB.
    # A missing pk means unconstrained.
    property_stay_rules: dict[int, tuple[int | None, int]] = field(default_factory=dict)
    # Convenience accessor for the "primary" currency. Set by `system_setup`
    # (or by the legacy fallback in the seed command).
    default_currency: Any = None
