"""API tests for /properties/{id}/services and /services/{pk} (GAP-037)."""

from __future__ import annotations

from datetime import date
from typing import cast

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from properties.factories import PropertyFactory
from properties.models import Property
from properties.models.services import PropertyService


@pytest.mark.django_db
def test_list_returns_only_this_propertys_services(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    other = cast(Property, PropertyFactory())
    PropertyService.objects.create(property=property_, name="Chef", copy="Summer chef")
    PropertyService.objects.create(property=other, name="Pool", copy="Heated pool")
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/services")
    assert response.status_code == 200, response.content
    names = {row["name"] for row in response.json()["results"]}
    assert names == {"Chef"}


@pytest.mark.django_db
def test_create_attaches_service_to_property(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/services",
        data={
            "name": "Private chef",
            "copy": "Breakfast and dinner daily",
            "notes": "Confirm dietary needs",
            "applies_from": "2026-06-01",
            "applies_to": "2026-08-31",
            "sort_order": 1,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    service = PropertyService.objects.get(pk=response.json()["id"])
    assert service.property_id == property_.pk
    assert service.name == "Private chef"
    assert service.applies_from == date(2026, 6, 1)


@pytest.mark.django_db
def test_create_allows_open_ended_band(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/services",
        data={"name": "Housekeeping", "copy": "Daily"},
        format="json",
    )
    assert response.status_code == 201, response.content
    service = PropertyService.objects.get(pk=response.json()["id"])
    assert service.applies_from is None
    assert service.applies_to is None


@pytest.mark.django_db
def test_create_rejects_inverted_band_with_400(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/services",
        data={
            "name": "Bad band",
            "copy": "x",
            "applies_from": "2026-08-31",
            "applies_to": "2026-06-01",
        },
        format="json",
    )
    assert response.status_code == 400, response.content
    assert not PropertyService.objects.filter(name="Bad band").exists()


@pytest.mark.django_db
def test_update_edits_service(api_client: APIClient, staff: User, property_: Property) -> None:
    service = PropertyService.objects.create(property=property_, name="Chef", copy="old")
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/services/{service.pk}",
        data={"copy": "new copy"},
        format="json",
    )
    assert response.status_code == 200, response.content
    service.refresh_from_db()
    assert service.copy == "new copy"


@pytest.mark.django_db
def test_patch_rejects_inverted_band_against_stored_end_with_400(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    # The stored band is open-ended; PATCHing only applies_from to a date after
    # the stored applies_to must 400 via the serializer's instance fallback —
    # never a 500 IntegrityError from the DB check constraint.
    service = PropertyService.objects.create(
        property=property_, name="Chef", copy="x", applies_to=date(2026, 6, 1)
    )
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/services/{service.pk}",
        data={"applies_from": "2026-08-31"},
        format="json",
    )
    assert response.status_code == 400, response.content
    service.refresh_from_db()
    assert service.applies_from is None


@pytest.mark.django_db
def test_patch_cannot_reparent_service_to_another_property(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    other = cast(Property, PropertyFactory())
    service = PropertyService.objects.create(property=property_, name="Chef", copy="x")
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/services/{service.pk}",
        data={"property": other.pk},
        format="json",
    )
    assert response.status_code == 200, response.content
    service.refresh_from_db()
    assert service.property_id == property_.pk  # read-only: reparent ignored


@pytest.mark.django_db
def test_delete_removes_service(api_client: APIClient, staff: User, property_: Property) -> None:
    service = PropertyService.objects.create(property=property_, name="Chef", copy="x")
    api_client.force_login(staff)
    response = api_client.delete(f"/api/v1/services/{service.pk}")
    assert response.status_code == 204
    assert not PropertyService.objects.filter(pk=service.pk).exists()


@pytest.mark.django_db
def test_requires_authentication(api_client: APIClient, property_: Property) -> None:
    response = api_client.get(f"/api/v1/properties/{property_.pk}/services")
    assert response.status_code in (401, 403)
