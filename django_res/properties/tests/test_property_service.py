from __future__ import annotations

from datetime import date

import pytest
from django.db import IntegrityError

from pricing.services.extras import date_ranges_overlap
from properties.models import Property, PropertyCategory, PropertyGroup, PropertyService, Region
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
def prop(group: PropertyGroup, category: PropertyCategory, region: Region) -> Property:
    return Property.objects.create(
        name="Sea View",
        display_name="Sea View",
        slug="sea-view",
        group=group,
        category=category,
        region=region,
    )


@pytest.mark.django_db
def test_create_dated_service(prop: Property) -> None:
    svc = PropertyService.objects.create(
        property=prop,
        name="Private chef",
        copy="A private chef prepares dinner nightly.",
        applies_from=date(2026, 6, 1),
        applies_to=date(2026, 8, 31),
    )
    assert svc.pk is not None
    assert prop.services.get() == svc
    # Optional internal notes default blank; copy is the guest-facing field.
    assert svc.notes == ""


@pytest.mark.django_db
def test_year_round_service_has_open_band(prop: Property) -> None:
    svc = PropertyService.objects.create(
        property=prop, name="Housekeeping", copy="Daily housekeeping."
    )
    assert svc.applies_from is None
    assert svc.applies_to is None


@pytest.mark.django_db
def test_applies_from_after_applies_to_rejected(prop: Property) -> None:
    with pytest.raises(IntegrityError):
        PropertyService.objects.create(
            property=prop,
            name="Backwards",
            copy="Invalid band.",
            applies_from=date(2026, 8, 31),
            applies_to=date(2026, 6, 1),
        )


@pytest.mark.django_db
def test_overlap_filter_matches_summer_not_autumn(prop: Property) -> None:
    """The engine selects active services whose band overlaps the stay; a
    summer-only chef applies in July but not November, and a year-round
    housekeeping service (null band) applies always."""
    chef = PropertyService.objects.create(
        property=prop,
        name="Private chef",
        copy="Chef.",
        applies_from=date(2026, 6, 1),
        applies_to=date(2026, 8, 31),
    )
    housekeeping = PropertyService.objects.create(
        property=prop, name="Housekeeping", copy="Housekeeping."
    )

    def applies(svc: PropertyService, frm: date, to: date) -> bool:
        return date_ranges_overlap(frm, to, svc.applies_from, svc.applies_to)

    july_from, july_to = date(2026, 7, 4), date(2026, 7, 11)
    nov_from, nov_to = date(2026, 11, 7), date(2026, 11, 14)

    assert applies(chef, july_from, july_to) is True
    assert applies(chef, nov_from, nov_to) is False
    assert applies(housekeeping, july_from, july_to) is True
    assert applies(housekeeping, nov_from, nov_to) is True


@pytest.mark.django_db
def test_ordering_by_sort_order(prop: Property) -> None:
    second = PropertyService.objects.create(property=prop, name="B", copy="b", sort_order=2)
    first = PropertyService.objects.create(property=prop, name="A", copy="a", sort_order=1)
    assert list(prop.services.all()) == [first, second]
