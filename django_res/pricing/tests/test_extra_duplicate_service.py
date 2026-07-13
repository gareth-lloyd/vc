"""Service tests for `duplicate_extra` (SMELL-009).

Field-copy fidelity is pinned at the API level in `test_api_extras.py`
(characterisation of the pre-extraction endpoint); this file pins the
idempotency semantics — including the deliberate destination-property key
scope: the same key with a different `target_property` is a different
logical operation and yields a second clone.
"""

from __future__ import annotations

from typing import cast

import pytest
from django.db import IntegrityError, transaction

from pricing.factories import ExtraFactory
from pricing.models import Extra
from pricing.services.duplication import duplicate_extra
from properties.factories import PropertyFactory
from properties.models import Property

pytestmark = pytest.mark.django_db


@pytest.fixture
def extra() -> Extra:
    return cast(Extra, ExtraFactory())


def test_clone_lands_on_source_property_by_default(extra: Extra) -> None:
    clone = duplicate_extra(extra)
    assert clone.pk != extra.pk
    assert clone.property_id == extra.property_id
    assert clone.name == f"{extra.name} (copy)"


def test_clone_reparents_to_target_property(extra: Extra) -> None:
    target = cast(Property, PropertyFactory())
    clone = duplicate_extra(extra, target_property=target)
    assert clone.property_id == target.pk
    extra.refresh_from_db()
    assert extra.property_id != target.pk


def test_retry_same_key_returns_original_clone(extra: Extra) -> None:
    first = duplicate_extra(extra, idempotency_key="k-1")
    count = Extra.objects.count()

    second = duplicate_extra(extra, idempotency_key="k-1")

    assert second.pk == first.pk
    assert Extra.objects.count() == count


def test_no_key_creates_a_new_clone_each_time(extra: Extra) -> None:
    first = duplicate_extra(extra)
    second = duplicate_extra(extra)
    assert first.pk != second.pk
    assert first.idempotency_key == "" == second.idempotency_key


def test_different_keys_create_distinct_clones(extra: Extra) -> None:
    first = duplicate_extra(extra, idempotency_key="k-1")
    second = duplicate_extra(extra, idempotency_key="k-2")
    assert first.pk != second.pk


def test_same_key_on_different_source_properties_coexists(extra: Extra) -> None:
    other = cast(Extra, ExtraFactory())
    assert other.property_id != extra.property_id

    first = duplicate_extra(extra, idempotency_key="shared")
    second = duplicate_extra(other, idempotency_key="shared")

    assert first.pk != second.pk


def test_same_key_different_target_is_a_different_operation(extra: Extra) -> None:
    # Deliberate: the pre-check scopes to the DESTINATION property, so the
    # same key aimed at two targets clones twice rather than returning the
    # first target's clone for the second target's request.
    target = cast(Property, PropertyFactory())

    in_place = duplicate_extra(extra, idempotency_key="k-t")
    reparented = duplicate_extra(extra, target_property=target, idempotency_key="k-t")

    assert in_place.pk != reparented.pk
    assert in_place.property_id == extra.property_id
    assert reparented.property_id == target.pk


def test_retry_with_target_returns_the_target_scoped_clone(extra: Extra) -> None:
    target = cast(Property, PropertyFactory())
    first = duplicate_extra(extra, target_property=target, idempotency_key="k-t2")
    second = duplicate_extra(extra, target_property=target, idempotency_key="k-t2")
    assert second.pk == first.pk


def test_db_backstop_rejects_second_row_with_same_property_and_key(extra: Extra) -> None:
    # FG-010: a racing loser past the pre-check must fail loudly on the
    # partial-unique constraint rather than silently duplicate.
    duplicate_extra(extra, idempotency_key="k-race")

    with pytest.raises(IntegrityError), transaction.atomic():
        Extra.objects.create(
            property=extra.property,
            name="racer",
            kind=extra.kind,
            calc=extra.calc,
            amount=extra.amount,
            currency=extra.currency,
            idempotency_key="k-race",
        )
