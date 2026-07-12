"""Unit tests for `pricing.services.rates.pick_band_for_night`.

The engine relies on three outcomes from the rate-picker per night:

* a matching band was found — quote the night at that band's nightly,
* a period covers the night but the party is outside every band — raise
  `PartyOutOfRange` (the legacy `09-departures.md` bug #2 regression),
* no period covers the night at all — raise `NoRateAvailable`.

Distinguishing the last two used to require a second nested loop
(`any_rule_covers_night`). The tagged-result API folds the disambiguation
into the single pass that walks the periods-by-bands grid (GAP-056).

The picker is pure (reads only `date_from`/`date_to`/`pk`/party bounds), so
these tests build unsaved `RatePeriod` / `RateBand` instances directly.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.exceptions import NoRateAvailable
from pricing.models import RateBand, RatePeriod
from pricing.services.rates import (
    NoCoverage,
    OutOfRange,
    Picked,
    pick_band_for_night,
    rule_base_nightly,
    rule_nightly,
)


def _period(pk: int, date_from: date, date_to: date) -> RatePeriod:
    return RatePeriod(id=pk, date_from=date_from, date_to=date_to)


def _band(pk: int, period_pk: int, min_party: int, max_party: int, nightly: str) -> RateBand:
    return RateBand(
        id=pk,
        period_id=period_pk,
        min_party=min_party,
        max_party=max_party,
        nightly=Decimal(nightly),
    )


# --- rule_nightly / rule_base_nightly (Q-018 reductions) ---------------------
#
# `rule_nightly` is the engine's single price read: it must return the
# *effective* (reduced) price, while `rule_base_nightly` keeps returning the
# base for the "reduced from X" figure. Pure properties — unsaved instances.


def test_rule_nightly_no_reduction_returns_base() -> None:
    band = RateBand(nightly=Decimal("200.00"))
    assert rule_nightly(band) == Decimal("200.00")
    assert rule_base_nightly(band) == Decimal("200.00")


def test_rule_nightly_percent_reduction() -> None:
    band = RateBand(nightly=Decimal("200.00"), reduction_percent=Decimal("25.00"))
    assert rule_nightly(band) == Decimal("150.00")
    assert rule_base_nightly(band) == Decimal("200.00")


def test_rule_nightly_fixed_reduction() -> None:
    band = RateBand(nightly=Decimal("200.00"), reduced_nightly=Decimal("170.00"))
    assert rule_nightly(band) == Decimal("170.00")
    assert rule_base_nightly(band) == Decimal("200.00")


def test_rule_nightly_weekly_only_percent_quantization_order() -> None:
    """Weekly-only + percent: the effective weekly quantizes FIRST, then /7.

    50% off 100.03 = 50.015 -> 50.02 (HALF_EVEN), /7 = 7.1457... -> 7.15.
    Dividing first would give 14.29 x 0.5 = 7.145 -> 7.14 — the order is
    observable, so pin it.
    """
    band = RateBand(weekly=Decimal("100.03"), reduction_percent=Decimal("50.00"))
    assert rule_nightly(band) == Decimal("7.15")
    assert rule_base_nightly(band) == Decimal("14.29")


def test_rule_nightly_weekly_fixed_reduction() -> None:
    band = RateBand(weekly=Decimal("1400.00"), reduced_weekly=Decimal("1190.00"))
    assert rule_nightly(band) == Decimal("170.00")
    assert rule_base_nightly(band) == Decimal("200.00")


def test_rule_nightly_poa_still_raises() -> None:
    band = RateBand(id=99, is_poa=True)
    with pytest.raises(NoRateAvailable):
        rule_nightly(band)
    with pytest.raises(NoRateAvailable):
        rule_base_nightly(band)


def test_pick_rule_returns_picked_with_matching_band() -> None:
    """A band whose period covers the night and whose bracket covers the party
    returns `Picked`."""
    period = _period(1, date(2026, 6, 1), date(2026, 8, 31))
    band = _band(11, period.pk, 1, 8, "100.00")

    result = pick_band_for_night([period], {period.pk: [band]}, night=date(2026, 6, 10), party=4)

    assert isinstance(result, Picked)
    assert result.period == period
    assert result.rule == band


def test_pick_rule_returns_out_of_range_when_no_party_matches() -> None:
    """A period covers the night but the party falls outside every band."""
    period = _period(1, date(2026, 6, 1), date(2026, 8, 31))
    small = _band(11, period.pk, 1, 8, "100.00")
    mid = _band(12, period.pk, 9, 12, "250.00")

    result = pick_band_for_night(
        [period], {period.pk: [small, mid]}, night=date(2026, 6, 10), party=20
    )

    assert isinstance(result, OutOfRange)


def test_pick_rule_returns_no_coverage_when_no_period_covers() -> None:
    """No period covers the requested night."""
    period = _period(1, date(2026, 6, 1), date(2026, 6, 30))
    band = _band(11, period.pk, 1, 8, "100.00")

    result = pick_band_for_night([period], {period.pk: [band]}, night=date(2026, 9, 1), party=4)

    assert isinstance(result, NoCoverage)


def test_pick_rule_returns_no_coverage_with_no_bands_at_all() -> None:
    """A covering period with no bands is `NoCoverage`, not `OutOfRange`."""
    period = _period(1, date(2026, 6, 1), date(2026, 8, 31))

    result = pick_band_for_night([period], {period.pk: []}, night=date(2026, 6, 10), party=4)

    assert isinstance(result, NoCoverage)


def test_pick_rule_lowest_band_pk_wins_across_overlapping_periods() -> None:
    """Periods are the disjoint date axis, but expand-phase / projected data can
    still carry overlapping periods; the LOWEST-pk matching band wins regardless
    of period list order (mirrors the carry-forward trim, so projected and
    materialised quotes agree). Flipping the list order does not change it."""
    wide = _period(2, date(2026, 6, 1), date(2026, 8, 31))
    narrow = _period(1, date(2026, 6, 10), date(2026, 6, 15))
    wide_band = _band(11, wide.pk, 1, 8, "100.00")  # lower pk
    narrow_band = _band(12, narrow.pk, 1, 8, "300.00")  # higher pk
    rules = {wide.pk: [wide_band], narrow.pk: [narrow_band]}

    for order in ([wide, narrow], [narrow, wide]):
        result = pick_band_for_night(order, rules, night=date(2026, 6, 12), party=4)
        assert isinstance(result, Picked)
        assert result.rule == wide_band  # lowest pk, whatever the order
        assert result.period == wide


def test_pick_rule_falls_through_to_next_period_on_party_miss() -> None:
    """A band whose period covers the night but whose bracket excludes the party
    must not shadow a matching band on another covering period — and must still
    count towards the OutOfRange/NoCoverage distinction."""
    small_period = _period(1, date(2026, 6, 1), date(2026, 8, 31))
    large_period = _period(2, date(2026, 6, 1), date(2026, 8, 31))
    small = _band(11, small_period.pk, 1, 8, "100.00")
    large = _band(12, large_period.pk, 9, 12, "250.00")

    result = pick_band_for_night(
        [small_period, large_period],
        {small_period.pk: [small], large_period.pk: [large]},
        night=date(2026, 6, 10),
        party=10,
    )

    assert isinstance(result, Picked)
    assert result.period == large_period
    assert result.rule == large


def test_pick_rule_in_memory_duplicate_resolves_to_lowest_pk() -> None:
    """Projected (unsaved) bands can collide after Feb-29 date mapping — no DB
    constraint applies to them; the lowest pk wins deterministically."""
    period = _period(1, date(2027, 6, 1), date(2027, 6, 30))
    first = _band(11, period.pk, 1, 8, "100.00")
    second = _band(12, period.pk, 1, 8, "300.00")

    result = pick_band_for_night(
        [period], {period.pk: [second, first]}, night=date(2027, 6, 12), party=4
    )

    assert isinstance(result, Picked)
    assert result.rule == first
