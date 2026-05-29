"""Factory smoke tests — every factory must build a valid, persisted row."""

from __future__ import annotations

from typing import cast

import pytest

from properties import factories, models
from properties.enums import ImageKind, PropertyStatus

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


def test_villa_manifest_lists_only_entries_with_imagery() -> None:
    """The committed pool drives manifest-coherent seeding; every returned
    entry must have the keys the `properties` stage reads and a `hero.jpg`.

    Skips when the (optional) pool is absent — the seeder falls back to random
    data without it, so a checkout that has removed seed_data/ stays green."""
    villas = factories.villa_manifest()
    if not villas:
        pytest.skip("villa image pool not present (core/seed_data/villa_images)")
    required = {"slug", "display_name", "location_tag", "country_iso2", "style_anchor"}
    for villa in villas:
        assert required <= villa.keys()
        assert (factories._SEED_IMAGE_ROOT / villa["slug"] / "hero.jpg").is_file()


def test_property_factory_draws_identity_and_hero_from_manifest_villa() -> None:
    """`children__villa` makes the description and HERO image come from the
    manifest villa rather than the random/placeholder fallback.

    Skips without the optional image pool (see the manifest test above)."""
    villas = factories.villa_manifest()
    if not villas:
        pytest.skip("villa image pool not present (core/seed_data/villa_images)")
    villa = villas[0]
    region = factories.RegionFactory(
        country=factories.CountryFactory(iso2=villa["country_iso2"]),
        name="Test locality",
    )
    prop = cast(
        models.Property,
        factories.PropertyFactory(
            display_name=villa["display_name"],
            region=region,
            children__villa=villa,
        ),
    )
    assert prop.display_name == villa["display_name"]
    assert prop.descriptions.get().body == villa["style_anchor"].strip()
    # A real JPEG, not the ~70-byte 1x1 placeholder.
    assert prop.images.get(kind=ImageKind.HERO).image.size > 1000


def test_room_and_feature_factories() -> None:
    room = factories.RoomFactory()
    assert room.beds.double >= 0
    feature = cast(models.Feature, factories.FeatureFactory())
    assert feature.category_id is not None


def test_nearby_place_type_factory_is_idempotent_on_name() -> None:
    n1 = cast(models.NearbyPlaceType, factories.NearbyPlaceTypeFactory(name="Beach"))
    n2 = cast(models.NearbyPlaceType, factories.NearbyPlaceTypeFactory(name="Beach"))
    assert n1.pk == n2.pk
    assert models.NearbyPlaceType.objects.filter(name="Beach").count() == 1


def test_property_nearby_place_factory_builds_row() -> None:
    pnp = cast(models.PropertyNearbyPlace, factories.PropertyNearbyPlaceFactory())
    assert pnp.pk is not None
    assert pnp.property_id is not None
    assert pnp.place_type_id is not None
    assert pnp.distance_km > 0


def test_collection_slug_unique_across_runs() -> None:
    c1 = cast(models.Collection, factories.CollectionFactory())
    c2 = cast(models.Collection, factories.CollectionFactory())
    assert c1.slug != c2.slug


def test_property_contact_assignment_factory() -> None:
    # Caller supplies the Contact; factory does not pull `accounts` in.
    from accounts.factories import ContactFactory

    contact = ContactFactory()
    assignment = cast(
        models.PropertyContactAssignment,
        factories.PropertyContactAssignmentFactory(contact=contact),
    )
    assert assignment.pk is not None
    assert assignment.is_primary is False


def test_changeover_rule_factory_window_is_valid() -> None:
    rule = cast(models.ChangeOverRule, factories.ChangeOverRuleFactory())
    assert rule.ends_on >= rule.starts_on
