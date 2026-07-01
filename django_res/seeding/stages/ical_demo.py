"""Pre-seed a single property under a fixed slug for the iCal demo command.

The `demo_ical` management command (`reservations.management.commands.demo_ical`)
attaches calendar feeds, owner blocks and conflicts to the property at
`PROPERTY_SLUG`. Seeding that property here — with a basic rate plan so it
prices like a real villa — lets a live demo run against realistic data without
baking a machine-specific slug into the command's source.

Idempotent: skipped when the property already exists, so additive reseeds never
collide on the unique slug. Deliberately NOT appended to `ctx.properties`, so
downstream stages (bookings, gallery, …) leave it alone and the demo command
owns its lifecycle.

The name differs from the command's own minimal fallback ("iCal Demo Villa") so
`demo_ical --reset` treats this as a pre-existing property and strips only its
demo attachments, never the property itself.
"""

from __future__ import annotations

import random

from pricing.factories import RateBandFactory, RatePeriodFactory, RatePlanFactory
from properties.factories import PropertyFactory
from properties.models import Property
from seeding._pricing_helpers import (
    assign_commission,
    build_seasonal_periods,
    draw_base_nightly,
    seed_included_services,
)
from seeding.context import SeedContext
from seeding.registry import Stage, register

ICAL_DEMO_SLUG = "ical-demo-villa"
ICAL_DEMO_NAME = "Demo iCal Villa"


def _run(ctx: SeedContext) -> int:
    if Property.objects.filter(slug=ICAL_DEMO_SLUG).exists():
        return 0
    prop = PropertyFactory(slug=ICAL_DEMO_SLUG, name=ICAL_DEMO_NAME)
    currency = ctx.default_currency
    plan = RatePlanFactory(property=prop, currency=currency)
    seed_included_services(prop, 0)
    # Match the active profile's pricing shape so the demo villa conforms to the
    # same invariants the portfolio plans satisfy — otherwise the seasonal
    # periods leak into the `happy` profile, which is meant to keep the legacy
    # single-period shape on *every* plan (and the smoke-test assertions enforce
    # exactly that).
    if ctx.knobs.realistic_pricing:
        # A fixed-seed local RNG (not ctx.rng) keeps the demo villa's pricing
        # deterministic without shifting the shared sequence other stages draw
        # from. Seasonal Low/Mid/Peak periods + commission mirror the realistic
        # portfolio plans.
        local_rng = random.Random(0)
        build_seasonal_periods(plan, draw_base_nightly(local_rng, currency.code), min_nights=1)
        assign_commission(local_rng, prop)
    else:
        # Legacy single 1-30 period, matching the happy portfolio (no commission
        # override — the villa keeps the factory's null-finance default).
        period = RatePeriodFactory(plan=plan, min_nights=1)
        RateBandFactory(period=period)
    return 1


register(Stage(name="ical_demo", run=_run, depends_on=("system_setup",)))
