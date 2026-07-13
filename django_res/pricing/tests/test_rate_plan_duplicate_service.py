"""Service tests for `duplicate_rate_plan` (SMELL-009).

The clone walk extracted from `RatePlanDuplicateView` plus FG-010 idempotency:
an optional key dedupes retries via a `(property, idempotency_key)` pre-check
backed by a partial-unique constraint. Field parity is asserted field-by-field
— a vague "counts match" test can't catch a silently dropped column.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

import pytest
from django.db import IntegrityError, transaction

from pricing.factories import RateBandFactory, RatePeriodFactory, RatePlanFactory
from pricing.models import RateBand, RatePeriod, RatePlan
from pricing.services.duplication import duplicate_rate_plan
from properties.enums import PriceBasis

pytestmark = pytest.mark.django_db


@pytest.fixture
def source_plan() -> RatePlan:
    """A plan with non-default values on every copyable field.

    `legacy_id` is set explicitly on all three levels — factories leave it
    None, which would mask the clone-must-not-copy-legacy_id rule (active
    loaders upsert on `legacy_id`; a copied one breaks the next delta load).
    """
    plan = cast(
        RatePlan,
        RatePlanFactory(
            name="Summer 2027",
            price_basis=PriceBasis.NET,
            prices_by_occupancy=True,
            fallback_nightly=Decimal("199.00"),
            effective_from=date(2027, 1, 1),
            effective_to=date(2027, 12, 31),
            is_active=False,
            notes="hand-tuned",
            legacy_id="legacy-plan-1",
        ),
    )
    low = cast(
        RatePeriod,
        RatePeriodFactory(
            plan=plan,
            name="Low season",
            date_from=date(2027, 1, 1),
            date_to=date(2027, 5, 31),
            min_nights=3,
            max_nights=21,
            is_active=False,
            legacy_id="legacy-period-1",
        ),
    )
    high = cast(
        RatePeriod,
        RatePeriodFactory(
            plan=plan,
            name="High season",
            date_from=date(2027, 6, 1),
            date_to=date(2027, 9, 30),
            legacy_id="legacy-period-2",
        ),
    )
    RateBandFactory(
        period=low,
        min_party=1,
        max_party=4,
        nightly=Decimal("250.00"),
        weekly=Decimal("1500.00"),
        reduction_percent=Decimal("10.00"),
        reduced_at=date(2027, 2, 1),
        reduction_reason="slow bookings",
        is_locked=True,
        is_approved=False,
        notes="band notes",
        legacy_id="legacy-band-1",
    )
    RateBandFactory(
        period=low,
        min_party=5,
        max_party=8,
        nightly=Decimal("400.00"),
        weekly=None,
        reduced_nightly=Decimal("360.00"),
        legacy_id="legacy-band-2",
    )
    RateBandFactory(
        period=high,
        min_party=1,
        max_party=8,
        nightly=None,
        weekly=None,
        is_poa=True,
        legacy_id="legacy-band-3",
    )
    return plan


def test_clone_copies_every_plan_field(source_plan: RatePlan) -> None:
    clone = duplicate_rate_plan(source_plan)

    assert clone.pk != source_plan.pk
    assert clone.property_id == source_plan.property_id
    assert clone.currency_id == source_plan.currency_id
    assert clone.name == "Summer 2027 (copy)"
    assert clone.price_basis == PriceBasis.NET
    assert clone.prices_by_occupancy is True
    assert clone.fallback_nightly == Decimal("199.00")
    assert clone.effective_from == date(2027, 1, 1)
    assert clone.effective_to == date(2027, 12, 31)
    assert clone.is_active is False
    assert clone.notes == "hand-tuned"


def test_clone_nulls_legacy_id_on_all_levels(source_plan: RatePlan) -> None:
    # Deliberate behaviour fix over the old view walk (Gareth-approved): the
    # clone is not the legacy row, so a copied legacy_id would make
    # RatePlanLoader/RateBandLoader upsert onto the clone on the next delta
    # load.
    clone = duplicate_rate_plan(source_plan)

    assert clone.legacy_id is None
    assert list(clone.periods.values_list("legacy_id", flat=True)) == [None, None]
    assert list(
        RateBand.objects.filter(period__plan=clone).values_list("legacy_id", flat=True)
    ) == [None, None, None]


def test_clone_copies_periods_and_bands_field_by_field(source_plan: RatePlan) -> None:
    clone = duplicate_rate_plan(source_plan)

    low, high = clone.periods.order_by("date_from")
    assert (low.name, low.date_from, low.date_to) == (
        "Low season",
        date(2027, 1, 1),
        date(2027, 5, 31),
    )
    assert (low.min_nights, low.max_nights, low.is_active) == (3, 21, False)
    assert (high.name, high.date_from, high.date_to) == (
        "High season",
        date(2027, 6, 1),
        date(2027, 9, 30),
    )

    reduced_pct, reduced_fixed = low.bands.order_by("min_party")
    assert reduced_pct.period_id == low.pk
    assert (reduced_pct.min_party, reduced_pct.max_party) == (1, 4)
    assert (reduced_pct.nightly, reduced_pct.weekly) == (Decimal("250.00"), Decimal("1500.00"))
    assert reduced_pct.reduction_percent == Decimal("10.00")
    assert (reduced_pct.reduced_nightly, reduced_pct.reduced_weekly) == (None, None)
    assert reduced_pct.reduced_at == date(2027, 2, 1)
    assert reduced_pct.reduction_reason == "slow bookings"
    assert (reduced_pct.is_poa, reduced_pct.is_locked, reduced_pct.is_approved) == (
        False,
        True,
        False,
    )
    assert reduced_pct.notes == "band notes"

    assert (reduced_fixed.min_party, reduced_fixed.max_party) == (5, 8)
    assert (reduced_fixed.nightly, reduced_fixed.weekly) == (Decimal("400.00"), None)
    assert reduced_fixed.reduced_nightly == Decimal("360.00")

    poa = high.bands.get()
    assert (poa.is_poa, poa.nightly, poa.weekly) == (True, None, None)


def test_retry_same_key_returns_original_clone_without_new_rows(
    source_plan: RatePlan,
) -> None:
    first = duplicate_rate_plan(source_plan, idempotency_key="k-1")
    counts = (RatePlan.objects.count(), RatePeriod.objects.count(), RateBand.objects.count())

    second = duplicate_rate_plan(source_plan, idempotency_key="k-1")

    assert second.pk == first.pk
    assert (
        RatePlan.objects.count(),
        RatePeriod.objects.count(),
        RateBand.objects.count(),
    ) == counts


def test_no_key_creates_a_new_clone_each_time(source_plan: RatePlan) -> None:
    first = duplicate_rate_plan(source_plan)
    second = duplicate_rate_plan(source_plan)
    assert first.pk != second.pk


def test_different_keys_create_distinct_clones(source_plan: RatePlan) -> None:
    first = duplicate_rate_plan(source_plan, idempotency_key="k-1")
    second = duplicate_rate_plan(source_plan, idempotency_key="k-2")
    assert first.pk != second.pk
    assert first.idempotency_key == "k-1"
    assert second.idempotency_key == "k-2"


def test_same_key_on_different_properties_coexists(source_plan: RatePlan) -> None:
    other_plan = cast(RatePlan, RatePlanFactory(name="Other villa rates"))
    assert other_plan.property_id != source_plan.property_id

    first = duplicate_rate_plan(source_plan, idempotency_key="shared-key")
    second = duplicate_rate_plan(other_plan, idempotency_key="shared-key")

    assert first.pk != second.pk
    assert first.property_id != second.property_id


def test_db_backstop_rejects_second_row_with_same_property_and_key(
    source_plan: RatePlan,
) -> None:
    # FG-010: the pre-check is check-then-create, so a racing loser must fail
    # loudly on the partial-unique constraint rather than silently duplicate.
    duplicate_rate_plan(source_plan, idempotency_key="k-race")

    with pytest.raises(IntegrityError), transaction.atomic():
        RatePlan.objects.create(
            property=source_plan.property,
            currency=source_plan.currency,
            name="racer",
            effective_from=date(2027, 1, 1),
            idempotency_key="k-race",
        )


def test_blank_key_rows_do_not_collide(source_plan: RatePlan) -> None:
    # The constraint is partial (~Q(idempotency_key="")): keyless clones—and
    # every pre-existing row—must never 409 each other.
    first = duplicate_rate_plan(source_plan)
    second = duplicate_rate_plan(source_plan)
    assert first.idempotency_key == "" == second.idempotency_key
