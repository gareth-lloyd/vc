"""Validation tests for `PropertyContactAssignmentSerializer` (GAP-048 L2-2).

The serializer must enforce the contact-XOR-organisation rule and restrict the
organisation assignee to the `management_company` role.
"""

from __future__ import annotations

from typing import cast

import pytest

from accounts.enums import ContactRole
from accounts.factories import OrganisationFactory
from accounts.models import Organisation, Person
from properties.factories import PropertyContactAssignmentFactory, PropertyFactory
from properties.models import PropertyContactAssignment
from properties.serializers import PropertyContactAssignmentSerializer


@pytest.fixture
def contact(db: None) -> Person:
    return Person.objects.create(first_name="Owner", last_name="One")


@pytest.fixture
def organisation(db: None) -> Organisation:
    return cast(Organisation, OrganisationFactory())


@pytest.mark.django_db
def test_serializer_accepts_contact_only(contact: Person) -> None:
    serializer = PropertyContactAssignmentSerializer(
        data={"contact": contact.pk, "role": ContactRole.OWNER}
    )
    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_serializer_accepts_organisation_for_management_company(
    organisation: Organisation,
) -> None:
    serializer = PropertyContactAssignmentSerializer(
        data={
            "organisation": organisation.pk,
            "role": ContactRole.MANAGEMENT_COMPANY,
        }
    )
    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_serializer_rejects_organisation_for_non_management_role(
    organisation: Organisation,
) -> None:
    serializer = PropertyContactAssignmentSerializer(
        data={"organisation": organisation.pk, "role": ContactRole.OWNER}
    )
    assert not serializer.is_valid()


@pytest.mark.django_db
def test_serializer_rejects_both_contact_and_organisation(
    contact: Person, organisation: Organisation
) -> None:
    serializer = PropertyContactAssignmentSerializer(
        data={
            "contact": contact.pk,
            "organisation": organisation.pk,
            "role": ContactRole.MANAGEMENT_COMPANY,
        }
    )
    assert not serializer.is_valid()


@pytest.mark.django_db
def test_serializer_rejects_neither_contact_nor_organisation() -> None:
    serializer = PropertyContactAssignmentSerializer(data={"role": ContactRole.OWNER})
    assert not serializer.is_valid()


@pytest.mark.django_db
def test_serializer_exposes_organisation_detail_for_org_row(organisation: Organisation) -> None:
    assignment = cast(
        PropertyContactAssignment,
        PropertyContactAssignmentFactory(
            property=PropertyFactory(),
            organisation=organisation,
            role=ContactRole.MANAGEMENT_COMPANY,
        ),
    )
    data = PropertyContactAssignmentSerializer(assignment).data
    assert data["contact"] is None
    # Nested OrganisationSummarySerializer ({id, name, org_type, status}).
    assert data["organisation_detail"]["id"] == organisation.pk
    assert data["organisation_detail"]["name"] == organisation.name


@pytest.mark.django_db
def test_serializer_organisation_detail_is_none_for_person_row(contact: Person) -> None:
    assignment = cast(
        PropertyContactAssignment,
        PropertyContactAssignmentFactory(
            property=PropertyFactory(),
            contact=contact,
            role=ContactRole.OWNER,
        ),
    )
    data = PropertyContactAssignmentSerializer(assignment).data
    assert data["organisation_detail"] is None
