"""seed_dev pre-seeds a fixed-slug villa for the iCal demo command."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from properties.models import Property
from seeding.stages.ical_demo import ICAL_DEMO_NAME, ICAL_DEMO_SLUG

pytestmark = pytest.mark.django_db


def _seed() -> None:
    call_command(
        "seed_dev",
        "--properties",
        "4",
        "--bookings",
        "8",
        "--profile",
        "happy",
        "--seed",
        "1",
        stdout=StringIO(),
    )


def test_seed_creates_fixed_slug_demo_villa_with_pricing() -> None:
    _seed()

    prop = Property.objects.get(slug=ICAL_DEMO_SLUG)
    assert prop.name == ICAL_DEMO_NAME
    # Conforming seasonal pricing so the demo prices like a real villa.
    plan = prop.rate_plans.get()
    assert {c.name for c in plan.cards.all()} == {"Low", "Mid", "Peak"}
    assert prop.finance.commission_calculation_type


def test_seed_is_idempotent_on_the_demo_villa() -> None:
    _seed()
    _seed()

    # Additive reseeds must not duplicate the fixed-slug villa.
    assert Property.objects.filter(slug=ICAL_DEMO_SLUG).count() == 1
