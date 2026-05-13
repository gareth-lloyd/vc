from __future__ import annotations

import pytest

from properties.enums import (
    AvailabilityDefault,
    PrefilledChangeOverDay,
    PriceBasis,
)
from properties.models import (
    GroupSettings,
    Property,
    PropertyCategory,
    PropertyGroup,
    PropertySettings,
    Region,
)
from properties.models.geo import Country


@pytest.fixture
def category(db: None) -> PropertyCategory:
    return PropertyCategory.objects.create(name="Villa", slug="villa")


@pytest.fixture
def country(db: None) -> Country:
    country, _ = Country.objects.get_or_create(
        iso2="GB",
        defaults={"name": "United Kingdom", "iso3": "GBR"},
    )
    return country


@pytest.fixture
def region(country: Country) -> Region:
    return Region.objects.create(country=country, name="Cornwall", slug="cornwall")


@pytest.fixture
def group(db: None) -> PropertyGroup:
    return PropertyGroup.objects.create(name="Test group")


@pytest.fixture
def prop(
    group: PropertyGroup,
    category: PropertyCategory,
    region: Region,
) -> Property:
    return Property.objects.create(
        name="Sea View",
        display_name="Sea View",
        slug="sea-view",
        group=group,
        category=category,
        region=region,
    )


@pytest.mark.django_db
def test_property_group_post_save_creates_group_settings() -> None:
    group = PropertyGroup.objects.create(name="Auto-create test")

    assert GroupSettings.objects.filter(group=group).exists()
    gs = group.settings
    # Defaults are applied.
    assert gs.availability_default == AvailabilityDefault.AVAILABLE
    assert gs.bookings_require_pre_approval is False
    assert gs.requires_enquiry_first is False
    assert gs.changeover_day == PrefilledChangeOverDay.ANY
    assert gs.min_nights_rental == 1
    assert gs.prices_entered_as == PriceBasis.GROSS


@pytest.mark.django_db
def test_property_group_resave_does_not_replace_group_settings() -> None:
    group = PropertyGroup.objects.create(name="Stable settings")
    settings_pk = group.settings.pk

    group.description = "Updated"
    group.save()

    group.refresh_from_db()
    assert group.settings.pk == settings_pk


@pytest.mark.django_db
def test_property_settings_effective_returns_own_value_when_set(prop: Property) -> None:
    PropertySettings.objects.create(
        property=prop,
        availability_default=AvailabilityDefault.ON_REQUEST,
        min_nights_rental=7,
    )

    assert prop.settings.effective("availability_default") == AvailabilityDefault.ON_REQUEST
    assert prop.settings.effective("min_nights_rental") == 7


@pytest.mark.django_db
def test_property_settings_effective_falls_back_to_group(prop: Property) -> None:
    # Tweak the group-level fallback first.
    group_settings = prop.group.settings
    group_settings.availability_default = AvailabilityDefault.UNAVAILABLE
    group_settings.min_nights_rental = 4
    group_settings.save()

    PropertySettings.objects.create(property=prop)  # All inheritable fields null.

    assert prop.settings.effective("availability_default") == AvailabilityDefault.UNAVAILABLE
    assert prop.settings.effective("min_nights_rental") == 4


@pytest.mark.django_db
def test_property_settings_effective_rejects_unknown_attr(prop: Property) -> None:
    PropertySettings.objects.create(property=prop)

    with pytest.raises(AttributeError):
        prop.settings.effective("not_a_real_field")
