"""`DeclarativeLoader` contract + the declarative lookup loaders that had no
transform coverage (BUG-030 test-coverage sweep): NearbyPlaceTypeLoader,
GuestPreferenceTypeLoader."""

from __future__ import annotations

from typing import ClassVar

import pytest
from django.db.models import Model

from data_migration.declarative import DeclarativeLoader, FkLookupError
from data_migration.loaders.lookups import NearbyPlaceTypeLoader
from data_migration.loaders.preferences import GuestPreferenceTypeLoader
from properties.factories import NearbyPlaceTypeFactory
from properties.models.geo import NearbyPlaceType, PropertyNearbyPlace


class _PlaceLoader(DeclarativeLoader):
    """A minimal declarative mapping with one rename and one FK, for the
    contract tests."""

    name = "test_place"
    legacy_table = "VillaNearBy"
    target_model = PropertyNearbyPlace
    field_map: ClassVar[dict[str, str]] = {"Name": "name"}
    fk_map: ClassVar[dict[str, tuple[type[Model], str]]] = {
        "TypeId": (NearbyPlaceType, "place_type")
    }


class _LenientPlaceLoader(_PlaceLoader):
    skip_if_missing_fk = True


def test_declarative_query_selects_pk_renames_and_fks_sorted() -> None:
    assert _PlaceLoader().legacy_query == "SELECT Id, Name, TypeId FROM VillaNearBy ORDER BY Id"


@pytest.mark.django_db
def test_declarative_transform_renames_and_resolves_fks_by_legacy_id() -> None:
    place_type = NearbyPlaceTypeFactory(legacy_id="7")
    kwargs = _PlaceLoader().transform({"Id": 1, "Name": "Beach", "TypeId": 7})
    assert kwargs == {"name": "Beach", "place_type": place_type}


@pytest.mark.django_db
def test_declarative_null_fk_maps_to_none() -> None:
    kwargs = _PlaceLoader().transform({"Id": 1, "Name": "Beach", "TypeId": None})
    assert kwargs == {"name": "Beach", "place_type": None}


@pytest.mark.django_db
def test_declarative_missing_fk_raises() -> None:
    with pytest.raises(FkLookupError, match=r"VillaNearBy\.TypeId=99"):
        _PlaceLoader().transform({"Id": 1, "Name": "Beach", "TypeId": 99})


@pytest.mark.django_db
def test_declarative_missing_fk_skips_when_skip_if_missing_fk() -> None:
    assert _LenientPlaceLoader().transform({"Id": 1, "Name": "Beach", "TypeId": 99}) is None


# --- NearbyPlaceTypeLoader ---


def test_nearby_place_type_transform() -> None:
    kwargs = NearbyPlaceTypeLoader().transform({"Id": 3, "Name": "  Beach  "})
    assert kwargs == {"name": "Beach", "icon": ""}


def test_nearby_place_type_blank_name_is_skipped() -> None:
    assert NearbyPlaceTypeLoader().transform({"Id": 3, "Name": "  "}) is None


def test_nearby_place_type_name_truncated_to_model_width() -> None:
    kwargs = NearbyPlaceTypeLoader().transform({"Id": 3, "Name": "x" * 200})
    assert kwargs is not None
    assert len(kwargs["name"]) == 128


# --- GuestPreferenceTypeLoader ---


@pytest.mark.parametrize(("raw_active", "expected"), [(1, True), (0, False), (None, False)])
def test_guest_preference_type_transform(raw_active: int | None, expected: bool) -> None:
    kwargs = GuestPreferenceTypeLoader().transform(
        {"Id": 4, "Name": " Sea view ", "IsActive": raw_active}
    )
    assert kwargs == {"name": "Sea view", "is_active": expected}


def test_guest_preference_type_blank_name_is_skipped() -> None:
    assert GuestPreferenceTypeLoader().transform({"Id": 4, "Name": "", "IsActive": 1}) is None
