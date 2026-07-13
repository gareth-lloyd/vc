"""Tests for `core.idempotency.find_by_key` and `IdempotencyConflict` (SMELL-009).

`find_by_key` is the dedicated-column twin of `find_by_meta_key`, for models
whose idempotency key lives in a `CharField` rather than `meta` JSON. Exercised
against `OwnerBlock`, which already carries the column — core's own tests may
import domain apps (`core.tests.** -> **` is an ignored import-linter edge).
"""

from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from django.utils import timezone

from core.exceptions import DomainError, IdempotencyConflict
from core.idempotency import find_by_key
from properties.factories import PropertyFactory
from properties.models import Property
from reservations.models import OwnerBlock
from reservations.models.owner_block import OwnerBlockSource

pytestmark = pytest.mark.django_db


def _block(prop: Property, key: str = "") -> OwnerBlock:
    # ICAL source so the `ownerblock_manual_requires_creator` constraint
    # doesn't demand a user row.
    return OwnerBlock.objects.create(
        property=prop,
        source=OwnerBlockSource.ICAL,
        idempotency_key=key,
        date_from=timezone.localdate() + timedelta(days=10),
        date_to=timezone.localdate() + timedelta(days=17),
    )


def test_none_key_returns_none_without_matching() -> None:
    prop = cast(Property, PropertyFactory())
    _block(prop, key="abc")
    assert find_by_key(OwnerBlock.objects.filter(property=prop), None) is None


def test_blank_key_returns_none_even_when_blank_rows_exist() -> None:
    # Blank is the column default — "" must mean "no idempotency requested",
    # never match the sea of keyless rows.
    prop = cast(Property, PropertyFactory())
    _block(prop, key="")
    assert find_by_key(OwnerBlock.objects.filter(property=prop), "") is None


def test_miss_returns_none() -> None:
    prop = cast(Property, PropertyFactory())
    _block(prop, key="abc")
    assert find_by_key(OwnerBlock.objects.filter(property=prop), "other") is None


def test_hit_returns_row() -> None:
    prop = cast(Property, PropertyFactory())
    block = _block(prop, key="abc")
    assert find_by_key(OwnerBlock.objects.filter(property=prop), "abc") == block


def test_scoping_respects_queryset() -> None:
    # Keys are unique per logical operation context, not globally: the same
    # key string on a different parent must stay invisible to a scoped lookup.
    prop = cast(Property, PropertyFactory())
    other_prop = cast(Property, PropertyFactory())
    _block(other_prop, key="abc")
    assert find_by_key(OwnerBlock.objects.filter(property=prop), "abc") is None


def test_idempotency_conflict_is_a_409_domain_error() -> None:
    exc = IdempotencyConflict("racing duplicate")
    assert isinstance(exc, DomainError)
    assert exc.code == "idempotency_conflict"
    assert exc.status_code == 409
