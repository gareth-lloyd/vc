"""API tests for /properties — CRUD + lifecycle actions."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from accounts.models import User
from properties.enums import ImageKind, PropertyStatus
from properties.models import (
    Property,
    PropertyCategory,
    PropertyGroup,
    PropertyImage,
    PropertyLocation,
    Region,
)


@pytest.mark.django_db
def test_list_properties_requires_authentication(
    api_client: APIClient, property_: Property
) -> None:
    response = api_client.get("/api/v1/properties")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_list_properties_returns_results(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.get("/api/v1/properties")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    slugs = {row["slug"] for row in payload["results"]}
    assert property_.slug in slugs


@pytest.mark.django_db
def test_list_orders_collisions_deterministically(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    group: PropertyGroup,
    region: Region,
) -> None:
    """Equal names must fall back to ascending id so page boundaries are stable.

    Without a total ordering, page-number pagination over name-only sorting can
    duplicate or skip rows — the quote builder pages through these candidates.
    """
    created = [
        Property.objects.create(
            name="Shared Name",
            display_name="Shared Name",
            slug=f"shared-{i}",
            category=category,
            group=group,
            region=region,
        )
        for i in range(3)
    ]
    api_client.force_login(staff)
    response = api_client.get("/api/v1/properties", {"q": "Shared Name"})
    assert response.status_code == 200
    ids = [row["id"] for row in response.json()["results"]]
    assert ids == sorted(c.id for c in created)


@pytest.mark.django_db
def test_create_property_as_staff(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    group: PropertyGroup,
    region: Region,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/properties",
        data={
            "name": "Fresh Villa",
            "display_name": "Fresh Villa",
            "slug": "fresh-villa",
            "category": category.pk,
            "group": group.pk,
            "region": region.pk,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    payload = response.json()
    assert payload["slug"] == "fresh-villa"
    assert payload["status"] == PropertyStatus.DRAFT.value
    # A default location is provisioned on create so its timezone/address are
    # immediately editable (consistent with the loader/factory).
    location = PropertyLocation.objects.get(property_id=payload["id"])
    assert location.country == region.country
    assert location.timezone == "Europe/London"


@pytest.mark.django_db
def test_create_property_rejected_for_viewer(
    api_client: APIClient,
    viewer: User,
    category: PropertyCategory,
    group: PropertyGroup,
    region: Region,
) -> None:
    api_client.force_login(viewer)
    response = api_client.post(
        "/api/v1/properties",
        data={
            "name": "Fresh Villa",
            "display_name": "Fresh Villa",
            "slug": "fresh-villa",
            "category": category.pk,
            "group": group.pk,
            "region": region.pk,
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_detail_by_id_or_slug(api_client: APIClient, staff: User, property_: Property) -> None:
    api_client.force_login(staff)
    by_id = api_client.get(f"/api/v1/properties/{property_.pk}")
    by_slug = api_client.get(f"/api/v1/properties/{property_.slug}")
    assert by_id.status_code == 200
    assert by_slug.status_code == 200
    assert by_id.json()["id"] == by_slug.json()["id"]


@pytest.mark.django_db
def test_detail_hero_image_url(api_client: APIClient, staff: User, property_: Property) -> None:
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/properties/{property_.pk}")
    assert response.status_code == 200
    assert response.json()["hero_image_url"] is None

    PropertyImage.objects.create(
        property=property_,
        kind=ImageKind.GALLERY,
        image=SimpleUploadedFile("gallery.jpg", b"x", content_type="image/jpeg"),
    )
    hero = PropertyImage.objects.create(
        property=property_,
        kind=ImageKind.HERO,
        image=SimpleUploadedFile("hero.jpg", b"x", content_type="image/jpeg"),
    )

    response = api_client.get(f"/api/v1/properties/{property_.pk}")
    assert response.status_code == 200
    assert response.json()["hero_image_url"] == hero.image.url


@pytest.mark.django_db
def test_patch_property(api_client: APIClient, staff: User, property_: Property) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}",
        data={"display_name": "Renamed Villa"},
        format="json",
    )
    assert response.status_code == 200, response.content
    property_.refresh_from_db()
    assert property_.display_name == "Renamed Villa"


@pytest.mark.django_db
def test_activate_transitions_status(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/properties/{property_.pk}:activate")
    assert response.status_code == 200
    property_.refresh_from_db()
    assert property_.status == PropertyStatus.ACTIVE.value


@pytest.mark.django_db
def test_archive_then_restore(api_client: APIClient, staff: User, property_: Property) -> None:
    api_client.force_login(staff)
    api_client.post(f"/api/v1/properties/{property_.pk}:activate")
    archived = api_client.post(f"/api/v1/properties/{property_.pk}:archive")
    assert archived.status_code == 200
    property_.refresh_from_db()
    assert property_.status == PropertyStatus.ARCHIVED.value

    restored = api_client.post(f"/api/v1/properties/{property_.pk}:restore")
    assert restored.status_code == 200
    property_.refresh_from_db()
    assert property_.status == PropertyStatus.DRAFT.value


@pytest.mark.django_db
def test_archive_from_archived_returns_409(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    property_.status = PropertyStatus.ARCHIVED.value
    property_.save(update_fields=["status"])
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/properties/{property_.pk}:archive")
    assert response.status_code == 409
    assert response.json()["code"] == "invalid_transition"


@pytest.mark.django_db
def test_duplicate_creates_new_property(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/properties/{property_.pk}:duplicate", format="json")
    assert response.status_code == 201, response.content
    payload = response.json()
    assert payload["id"] != property_.pk
    assert payload["slug"] != property_.slug
    # The clone is provisioned with a location, like API-created properties.
    assert PropertyLocation.objects.filter(property_id=payload["id"]).exists()


@pytest.mark.django_db
def test_import_from_zoho_returns_501(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/properties/{property_.pk}:import-from-zoho")
    assert response.status_code == 501
    assert response.json()["code"] == "not_implemented"
