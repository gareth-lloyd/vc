"""Factory smoke tests — every factory must build a valid, persisted row."""

from __future__ import annotations

from typing import cast

import pytest

from properties import factories, models
from properties.enums import PropertyStatus

pytestmark = pytest.mark.django_db


def test_country_factory_reuses_seeded_iso_rows() -> None:
    """`properties.0009` pre-seeds 249 ISO countries; the factory must reuse
    them via get_or_create rather than violate the iso2 unique constraint."""
    before = models.Country.objects.count()
    country = cast(models.Country, factories.CountryFactory())
    assert country.pk is not None
    assert models.Country.objects.count() == before  # reused, not created


def test_region_factory_unique_across_runs() -> None:
    r1 = factories.RegionFactory()
    r2 = factories.RegionFactory()
    assert r1.slug != r2.slug


def test_property_factory_builds_full_graph() -> None:
    prop = cast(models.Property, factories.PropertyFactory())

    assert prop.status == PropertyStatus.ACTIVE
    # The 1:1 children the booking/pricing services walk must all exist.
    assert prop.location.country_id == prop.region.country_id
    assert prop.capacity.bedrooms >= 1
    assert prop.settings is not None
    assert prop.finance is not None
    assert prop.descriptions.exists()
    assert prop.hero_image() is not None
    # Group fallbacks the `effective()` resolvers depend on.
    assert prop.group.settings is not None
    assert prop.group.finance is not None
    assert prop.settings.effective("bookings_require_pre_approval") in (True, False)


def test_property_slug_unique_across_runs() -> None:
    assert factories.PropertyFactory().slug != factories.PropertyFactory().slug


def test_room_and_feature_factories() -> None:
    room = factories.RoomFactory()
    assert room.beds.double >= 0
    feature = cast(models.Feature, factories.FeatureFactory())
    assert feature.category_id is not None
