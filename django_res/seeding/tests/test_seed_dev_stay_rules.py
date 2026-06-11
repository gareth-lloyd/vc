"""Portfolio stay-rule contract: mixed/chaos must mirror the legacy prod shape
(88% of villas carry a specific changeover day — Saturday-heavy — and a
7-night minimum stay), every seeded stay on a constrained villa must conform
(start on the changeover weekday, whole weeks), and `happy` keeps the legacy
unconstrained shape byte-for-byte.

These run against an isolated transactional DB (no accumulation from other
tests), so the per-run distribution can be asserted directly.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from pricing.models.rate import RateCard
from properties.models import Property
from reservations.models.booking import Booking
from reservations.models.quotation import QuotationLine

# PrefilledChangeOverDay code -> date.weekday() for the *specific* days.
_DAY_WEEKDAY = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def _seed(profile: str, *, properties: int, bookings: int, seed: int) -> None:
    call_command(
        "seed_dev",
        "--properties",
        str(properties),
        "--bookings",
        str(bookings),
        "--profile",
        profile,
        "--seed",
        str(seed),
        stdout=StringIO(),
    )


@pytest.mark.django_db(transaction=True)
def test_seed_dev_mixed_assigns_stay_rules_and_conforms_stays() -> None:
    """One mixed portfolio asserted from every stay-rule angle (a single run —
    each `transaction=True` test flushes + reseeds the whole DB):

    * most villas constrained (specific day + 7-night min on settings AND on
      every rate card), but not all — the unconstrained floor holds;
    * Saturday dominates, mirroring legacy prod (72% of explicit days);
    * every booking and quotation line on a constrained villa starts on that
      villa's changeover weekday and spans whole weeks — the engine never had
      to shift or reject anything;
    * dashboard's today-anchored short stays only land on unconstrained villas
      (implied by the conformance assertion: a 3-night today-anchored stay on
      a constrained villa would fail it).
    """
    _seed("mixed", properties=10, bookings=40, seed=42)

    props = list(Property.objects.all())
    constrained = [p for p in props if p.settings.changeover_day in _DAY_WEEKDAY]
    unconstrained = [p for p in props if p.settings.changeover_day not in _DAY_WEEKDAY]
    days = sorted(str(p.settings.changeover_day) for p in constrained)
    assert len(constrained) >= 5, f"expected a mostly-constrained portfolio, days={days}"
    assert len(unconstrained) >= 2, "expected the unconstrained floor to hold"
    assert days.count("sat") > len(constrained) / 2, f"expected Saturday-heavy, days={days}"

    for prop in constrained:
        assert prop.settings.min_nights_rental == 7, prop
        cards = list(RateCard.objects.filter(plan__property=prop))
        assert cards, prop
        assert all(card.min_nights == 7 for card in cards), prop
        weekday = _DAY_WEEKDAY[str(prop.settings.changeover_day)]
        stays = [(b.date_from, b.date_to) for b in Booking.objects.filter(property=prop)] + [
            (line.date_from, line.date_to) for line in QuotationLine.objects.filter(property=prop)
        ]
        assert stays, f"constrained villa {prop.pk} should still host stays"
        for date_from, date_to in stays:
            assert date_from.weekday() == weekday, (prop.settings.changeover_day, date_from)
            nights = (date_to - date_from).days
            assert nights >= 7 and nights % 7 == 0, (date_from, date_to)


@pytest.mark.django_db(transaction=True)
def test_seed_dev_happy_keeps_unconstrained_shape() -> None:
    """The happy profile keeps the legacy shape: no changeover day, no
    minimum-stay floor on settings or cards."""
    _seed("happy", properties=4, bookings=6, seed=42)
    for prop in Property.objects.all():
        assert prop.settings.changeover_day is None, prop
        assert prop.settings.min_nights_rental is None, prop
    assert all(card.min_nights == 1 for card in RateCard.objects.all())
