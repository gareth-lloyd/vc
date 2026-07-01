from __future__ import annotations

from datetime import date
from typing import cast

import pytest
from django.db import IntegrityError

from accounts.enums import ContactRole
from accounts.factories import OrganisationFactory
from accounts.models import Organisation, Person
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


@pytest.fixture
def organisation(db: None) -> Organisation:
    return cast(Organisation, OrganisationFactory())


@pytest.fixture
def prop2(
    group: PropertyGroup,
    category: PropertyCategory,
    region: Region,
) -> Property:
    return Property.objects.create(
        name="Hill View",
        display_name="Hill View",
        slug="hill-view",
        group=group,
        category=category,
        region=region,
    )


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


# --- GAP-048 L2-2: Organisation assignee --------------------------------------


@pytest.mark.django_db
def test_assignment_requires_contact_xor_organisation_neither(prop: Property) -> None:
    """A row with neither a contact nor an organisation violates the XOR check."""
    with pytest.raises(IntegrityError):
        PropertyContactAssignment.objects.create(
            property=prop,
            role=ContactRole.MANAGEMENT_COMPANY,
        )


@pytest.mark.django_db
def test_assignment_rejects_both_contact_and_organisation(
    prop: Property, contact: Person, organisation: Organisation
) -> None:
    """A row with both a contact and an organisation violates the XOR check."""
    with pytest.raises(IntegrityError):
        PropertyContactAssignment.objects.create(
            property=prop,
            contact=contact,
            organisation=organisation,
            role=ContactRole.MANAGEMENT_COMPANY,
        )


@pytest.mark.django_db
def test_assignment_rejects_organisation_with_non_management_role(
    prop: Property, organisation: Organisation
) -> None:
    """An Organisation assignee is only valid for the management_company role —
    enforced at the DB so a loader/ORM write can't persist e.g. an org as OWNER."""
    with pytest.raises(IntegrityError):
        PropertyContactAssignment.objects.create(
            property=prop,
            organisation=organisation,
            role=ContactRole.OWNER,
        )


@pytest.mark.django_db
def test_assignment_person_may_hold_management_company_role(
    prop: Property, contact: Person
) -> None:
    """The org→role constraint only bites org rows; a Person may hold any role,
    including management_company (the legacy loader maps role id 5 to a Person)."""
    PropertyContactAssignment.objects.create(
        property=prop,
        contact=contact,
        role=ContactRole.MANAGEMENT_COMPANY,
    )


@pytest.mark.django_db
def test_assignment_accepts_organisation_only(prop: Property, organisation: Organisation) -> None:
    assignment = PropertyContactAssignment.objects.create(
        property=prop,
        organisation=organisation,
        role=ContactRole.MANAGEMENT_COMPANY,
    )
    assert assignment.contact_id is None
    assert assignment.organisation_id == organisation.pk


@pytest.mark.django_db
def test_assignment_org_unique_active_role(prop: Property, organisation: Organisation) -> None:
    other_org = cast(Organisation, OrganisationFactory())
    PropertyContactAssignment.objects.create(
        property=prop,
        organisation=organisation,
        role=ContactRole.MANAGEMENT_COMPANY,
    )
    # A second OPEN org assignment for a different org on the same (property, role)
    # is allowed (distinct organisation); but the SAME org twice collides.
    PropertyContactAssignment.objects.create(
        property=prop,
        organisation=other_org,
        role=ContactRole.MANAGEMENT_COMPANY,
    )
    with pytest.raises(IntegrityError):
        PropertyContactAssignment.objects.create(
            property=prop,
            organisation=organisation,
            role=ContactRole.MANAGEMENT_COMPANY,
        )


@pytest.mark.django_db
def test_assignment_org_can_reopen_after_end_date(
    prop: Property, organisation: Organisation
) -> None:
    PropertyContactAssignment.objects.create(
        property=prop,
        organisation=organisation,
        role=ContactRole.MANAGEMENT_COMPANY,
        end_date=date(2024, 1, 1),
    )
    # Closed row does not block a fresh open one for the same (property, org, role).
    PropertyContactAssignment.objects.create(
        property=prop,
        organisation=organisation,
        role=ContactRole.MANAGEMENT_COMPANY,
    )


@pytest.mark.django_db
def test_organisation_merge_dedupes_colliding_assignment(
    prop: Property, organisation: Organisation
) -> None:
    """Two orgs each holding an open assignment on the same (property, role): the
    merge must drop the colliding source row, not raise IntegrityError."""
    source = organisation
    target = cast(Organisation, OrganisationFactory())
    PropertyContactAssignment.objects.create(
        property=prop, organisation=source, role=ContactRole.MANAGEMENT_COMPANY
    )
    PropertyContactAssignment.objects.create(
        property=prop, organisation=target, role=ContactRole.MANAGEMENT_COMPANY
    )

    source.merge(target)

    assert not Organisation.objects.filter(pk=source.pk).exists()
    surviving = PropertyContactAssignment.objects.filter(
        property=prop, role=ContactRole.MANAGEMENT_COMPANY
    )
    assert surviving.count() == 1
    assert surviving.get().organisation_id == target.pk


@pytest.mark.django_db
def test_organisation_merge_moves_noncolliding_assignment(
    prop: Property, prop2: Property, organisation: Organisation
) -> None:
    """Assignments on distinct (property, role) move onto the target intact."""
    source = organisation
    target = cast(Organisation, OrganisationFactory())
    PropertyContactAssignment.objects.create(
        property=prop, organisation=source, role=ContactRole.MANAGEMENT_COMPANY
    )
    PropertyContactAssignment.objects.create(
        property=prop2, organisation=target, role=ContactRole.MANAGEMENT_COMPANY
    )

    source.merge(target)

    assert not Organisation.objects.filter(pk=source.pk).exists()
    assert (
        PropertyContactAssignment.objects.filter(
            organisation=target, role=ContactRole.MANAGEMENT_COMPANY
        ).count()
        == 2
    )
