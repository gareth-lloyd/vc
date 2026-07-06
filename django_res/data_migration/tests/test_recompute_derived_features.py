"""`recompute_derived_features` command — cutover backfill of GAP-067 derived
property features across every property.

The room save-path recomputes derived features live, but a legacy load +
room-attribute backfill writes assignments in bulk without going through that
path. This command sweeps all properties once so migrated data matches
API-created data. Idempotent; `--dry-run` reports without writing.
"""

from __future__ import annotations

from io import StringIO
from typing import cast

import pytest
from django.core.management import call_command

from properties.factories import (
    FeatureFactory,
    PropertyFactory,
    RoomAttributeFactory,
    RoomFactory,
)
from properties.models import (
    Feature,
    Property,
    PropertyFeature,
    Room,
    RoomAttribute,
    RoomAttributeAssignment,
)

pytestmark = pytest.mark.django_db


def _call(*args: str) -> str:
    out = StringIO()
    call_command("recompute_derived_features", *args, stdout=out)
    return out.getvalue()


def _property_implying(feature: Feature) -> Property:
    """A property with one room whose attribute implies `feature` — but no
    derived link yet (the assignment was written without the save-path hook)."""
    prop = cast(Property, PropertyFactory())
    room = cast(Room, RoomFactory(property=prop))
    attr = cast(RoomAttribute, RoomAttributeFactory(implies_property_feature=feature))
    RoomAttributeAssignment.objects.create(room=room, attribute=attr)
    return prop


def test_real_run_creates_derived_links() -> None:
    feature = cast(Feature, FeatureFactory())
    prop = _property_implying(feature)
    assert not PropertyFeature.objects.filter(property=prop).exists()

    out = _call()

    link = PropertyFeature.objects.get(property=prop, feature=feature)
    assert link.is_derived is True
    assert "1" in out  # reports at least one added link


def test_is_idempotent() -> None:
    feature = cast(Feature, FeatureFactory())
    prop = _property_implying(feature)
    _call()
    out = _call()

    assert PropertyFeature.objects.filter(property=prop, feature=feature).count() == 1
    # The second run adds nothing.
    assert "0 added" in out


def test_dry_run_reports_but_writes_nothing() -> None:
    feature = cast(Feature, FeatureFactory())
    prop = _property_implying(feature)

    out = _call("--dry-run")

    assert "[dry-run]" in out
    assert not PropertyFeature.objects.filter(property=prop).exists()
