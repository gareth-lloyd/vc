from __future__ import annotations

from datetime import date

import pytest
from django.db import IntegrityError

from accounts.enums import ContactRole
from accounts.models import Person
from properties.enums import ImageKind
from properties.models import (
    Collection,
    CollectionMembership,
    Property,
    PropertyCategory,
    PropertyContactAssignment,
    PropertyGroup,
    PropertyImage,
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


@pytest.fixture
def contact(db: None) -> Person:
    return Person.objects.create(first_name="Owner", last_name="One")


@pytest.mark.django_db
def test_collection_membership_unique_collection_property(prop: Property) -> None:
    collection = Collection.objects.create(name="Best of", slug="best-of")
    CollectionMembership.objects.create(collection=collection, property=prop)

    with pytest.raises(IntegrityError):
        CollectionMembership.objects.create(collection=collection, property=prop)


@pytest.mark.django_db
def test_property_image_single_active_hero(prop: Property) -> None:
    PropertyImage.objects.create(property=prop, image="x.jpg", kind=ImageKind.HERO)

    # A second active HERO on the same property is rejected.
    with pytest.raises(IntegrityError):
        PropertyImage.objects.create(
            property=prop,
            image="y.jpg",
            kind=ImageKind.HERO,
        )


@pytest.mark.django_db
def test_property_image_inactive_hero_allowed_alongside_active(prop: Property) -> None:
    PropertyImage.objects.create(
        property=prop,
        image="old.jpg",
        kind=ImageKind.HERO,
        is_active=False,
    )
    PropertyImage.objects.create(property=prop, image="new.jpg", kind=ImageKind.HERO)

    assert prop.images.filter(kind=ImageKind.HERO).count() == 2


@pytest.mark.django_db
def test_property_image_multiple_galleries_allowed(prop: Property) -> None:
    PropertyImage.objects.create(property=prop, image="a.jpg", kind=ImageKind.GALLERY)
    PropertyImage.objects.create(property=prop, image="b.jpg", kind=ImageKind.GALLERY)

    assert prop.images.count() == 2


@pytest.mark.django_db
def test_contact_assignment_unique_active_role(prop: Property, contact: Person) -> None:
    PropertyContactAssignment.objects.create(
        property=prop,
        contact=contact,
        role=ContactRole.OWNER,
    )

    with pytest.raises(IntegrityError):
        PropertyContactAssignment.objects.create(
            property=prop,
            contact=contact,
            role=ContactRole.OWNER,
        )


@pytest.mark.django_db
def test_contact_assignment_accepts_reconciled_roles(prop: Property, contact: Person) -> None:
    """GAP-048: villa_admin & management_company are valid roles (legacy ids 3 & 5,
    previously collapsed to manager / owners_rep on import). CharField choices are
    only enforced by model validation, so assert via full_clean."""
    for role in (ContactRole.VILLA_ADMIN, ContactRole.MANAGEMENT_COMPANY):
        assignment = PropertyContactAssignment(property=prop, contact=contact, role=role)
        assignment.full_clean()  # choices validation must pass
        assignment.save()
    assert PropertyContactAssignment.objects.filter(property=prop).count() == 2


@pytest.mark.django_db
def test_contact_assignment_can_reopen_after_end_date(prop: Property, contact: Person) -> None:
    PropertyContactAssignment.objects.create(
        property=prop,
        contact=contact,
        role=ContactRole.OWNER,
        end_date=date(2024, 1, 1),
    )

    # Same role can be reopened because the previous row is closed.
    PropertyContactAssignment.objects.create(
        property=prop,
        contact=contact,
        role=ContactRole.OWNER,
    )


@pytest.mark.django_db
def test_contact_assignment_only_one_primary_per_role(prop: Property, contact: Person) -> None:
    other = Person.objects.create(first_name="Owner", last_name="Two")
    PropertyContactAssignment.objects.create(
        property=prop,
        contact=contact,
        role=ContactRole.OWNER,
        is_primary=True,
    )

    with pytest.raises(IntegrityError):
        PropertyContactAssignment.objects.create(
            property=prop,
            contact=other,
            role=ContactRole.OWNER,
            is_primary=True,
        )
