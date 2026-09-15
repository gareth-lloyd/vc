"""`NearbyPlaceLoader.transform` (BUG-030 test-coverage sweep; only a query
test existed)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from data_migration.loaders.property_children import NearbyPlaceLoader
from properties.factories import NearbyPlaceTypeFactory, PropertyFactory

pytestmark = pytest.mark.django_db


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Id": 1,
        "PropertyId": "500",
        "TypeId": "7",
        "Name": "  Agios Gordios beach ",
        "Description": " Sandy. ",
        "Distance": Decimal("2.50"),
    }
    row.update(overrides)
    return row


def test_transform_resolves_property_and_type() -> None:
    prop = PropertyFactory(legacy_id="500")
    place_type = NearbyPlaceTypeFactory(legacy_id="7")
    assert NearbyPlaceLoader().transform(_row()) == {
        "property": prop,
        "place_type": place_type,
        "name": "Agios Gordios beach",
        "distance_km": Decimal("2.50"),
        "notes": "Sandy.",
    }


def test_transform_skips_unresolved_property() -> None:
    NearbyPlaceTypeFactory(legacy_id="7")
    assert NearbyPlaceLoader().transform(_row()) is None


def test_transform_skips_unresolved_place_type() -> None:
    PropertyFactory(legacy_id="500")
    assert NearbyPlaceLoader().transform(_row()) is None


def test_transform_skips_blank_name() -> None:
    PropertyFactory(legacy_id="500")
    NearbyPlaceTypeFactory(legacy_id="7")
    assert NearbyPlaceLoader().transform(_row(Name="  ")) is None


def test_transform_null_distance_is_zero() -> None:
    PropertyFactory(legacy_id="500")
    NearbyPlaceTypeFactory(legacy_id="7")
    kwargs = NearbyPlaceLoader().transform(_row(Distance=None))
    assert kwargs is not None
    assert kwargs["distance_km"] == 0
