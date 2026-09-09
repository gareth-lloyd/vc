"""The `features` stage also seeds the GAP-091 "Other information" tag
vocabulary (on every profile) and hangs two tags on each demo villa, so the
Features tab section has something to show on a fresh `seed_dev`.
"""

from __future__ import annotations

import random
from typing import cast

import pytest

from properties.factories import PropertyFactory
from properties.models import Feature, FeatureCategory, Property, PropertyFeature
from properties.other_information_catalog import (
    OTHER_INFORMATION_CATEGORY_SLUG,
    STARTER_TAGS,
)
from seeding.context import _PROFILES, Profile, SeedContext
from seeding.stages.features import _ensure_catalogue, _run

pytestmark = pytest.mark.django_db


def _ctx(
    properties: list[Property], profile: Profile = Profile.MIXED, seed: int = 0
) -> SeedContext:
    ctx = SeedContext(
        rng=random.Random(seed),
        knobs=_PROFILES[profile],
        n_properties=len(properties),
        n_bookings=0,
        n_users=0,
    )
    ctx.properties.extend(properties)
    return ctx


def _tag_slugs_by_property(properties: list[Property]) -> dict[int, set[str]]:
    links = PropertyFeature.objects.filter(
        property__in=properties,
        feature__category__slug=OTHER_INFORMATION_CATEGORY_SLUG,
    ).select_related("feature")
    out: dict[int, set[str]] = {p.pk: set() for p in properties}
    for link in links:
        out[link.property_id].add(link.feature.slug)
    return out


def _main_pks_by_property(properties: list[Property]) -> dict[int, set[int]]:
    links = PropertyFeature.objects.filter(property__in=properties).exclude(
        feature__category__slug=OTHER_INFORMATION_CATEGORY_SLUG
    )
    out: dict[int, set[int]] = {p.pk: set() for p in properties}
    for link in links:
        out[link.property_id].add(link.feature_id)
    return out


def test_stage_seeds_vocabulary_and_tags_every_demo_villa() -> None:
    properties = [cast(Property, PropertyFactory()) for _ in range(6)]

    _run(_ctx(properties))

    assert FeatureCategory.objects.filter(slug=OTHER_INFORMATION_CATEGORY_SLUG).exists()
    assert Feature.objects.filter(category__slug=OTHER_INFORMATION_CATEGORY_SLUG).count() == len(
        STARTER_TAGS
    )
    by_property = _tag_slugs_by_property(properties)
    assert all(len(slugs) == 2 for slugs in by_property.values()), by_property
    # More than one distinct pair across six villas — the picks vary.
    assert len({frozenset(slugs) for slugs in by_property.values()}) > 1


def test_vocabulary_is_seeded_even_when_the_profile_disables_features() -> None:
    assert _PROFILES[Profile.HAPPY].features_per_property == (0, 0)
    properties = [cast(Property, PropertyFactory())]

    assert _run(_ctx(properties, profile=Profile.HAPPY)) == 0

    assert Feature.objects.filter(category__slug=OTHER_INFORMATION_CATEGORY_SLUG).count() == len(
        STARTER_TAGS
    )
    assert not PropertyFeature.objects.filter(property__in=properties).exists()


def test_tag_assignment_is_deterministic_and_rerun_safe() -> None:
    properties = [cast(Property, PropertyFactory()) for _ in range(3)]

    _run(_ctx(properties))
    first = _tag_slugs_by_property(properties)
    _run(_ctx(properties))
    second = _tag_slugs_by_property(properties)

    assert first == second
    assert all(len(slugs) == 2 for slugs in first.values())


def test_main_picks_come_from_ctx_rng_alone() -> None:
    # Tags draw from a private RNG: the main picks must be exactly what a
    # fresh `Random(0)` yields when replayed with no extra draws in between.
    properties = [cast(Property, PropertyFactory()) for _ in range(4)]
    low, high = _PROFILES[Profile.MIXED].features_per_property

    _run(_ctx(properties, seed=0))

    catalogue = _ensure_catalogue()
    replay = random.Random(0)
    expected: dict[int, set[int]] = {}
    for prop in properties:
        n = min(replay.randint(low, high), len(catalogue))
        expected[prop.pk] = {f.pk for f in replay.sample(catalogue, k=n)}
    assert _main_pks_by_property(properties) == expected
