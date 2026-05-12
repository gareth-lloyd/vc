"""API tests for /properties/{id}/descriptions."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from properties.enums import DescriptionSection
from properties.models import Property, PropertyDescription


@pytest.mark.django_db
def test_put_creates_description(api_client: APIClient, staff: User, property_: Property) -> None:
    api_client.force_login(staff)
    response = api_client.put(
        f"/api/v1/properties/{property_.pk}/descriptions/overview",
        data={"body": "Overview body"},
        format="json",
    )
    assert response.status_code == 201, response.content
    assert PropertyDescription.objects.filter(
        property=property_, section=DescriptionSection.OVERVIEW
    ).exists()


@pytest.mark.django_db
def test_put_upserts_existing_description(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    PropertyDescription.objects.create(
        property=property_,
        section=DescriptionSection.OVERVIEW,
        body="Old body",
    )
    api_client.force_login(staff)
    response = api_client.put(
        f"/api/v1/properties/{property_.pk}/descriptions/overview",
        data={"body": "New body"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["body"] == "New body"


@pytest.mark.django_db
def test_get_section_returns_404_when_missing(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/descriptions/overview")
    assert response.status_code == 404


@pytest.mark.django_db
def test_list_descriptions_returns_present_sections(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    PropertyDescription.objects.create(
        property=property_,
        section=DescriptionSection.OVERVIEW,
        body="A",
    )
    PropertyDescription.objects.create(
        property=property_,
        section=DescriptionSection.HOUSE_RULES,
        body="B",
    )
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/descriptions")
    assert response.status_code == 200
    sections = {row["section"] for row in response.json()["results"]}
    assert sections == {"overview", "house_rules"}


@pytest.mark.django_db
def test_delete_removes_section(api_client: APIClient, staff: User, property_: Property) -> None:
    PropertyDescription.objects.create(
        property=property_,
        section=DescriptionSection.OVERVIEW,
        body="A",
    )
    api_client.force_login(staff)
    response = api_client.delete(f"/api/v1/properties/{property_.pk}/descriptions/overview")
    assert response.status_code == 204
    assert not PropertyDescription.objects.filter(
        property=property_, section=DescriptionSection.OVERVIEW
    ).exists()


@pytest.mark.django_db
def test_unknown_section_returns_404(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.put(
        f"/api/v1/properties/{property_.pk}/descriptions/garbage-section",
        data={"body": "X"},
        format="json",
    )
    assert response.status_code == 404
