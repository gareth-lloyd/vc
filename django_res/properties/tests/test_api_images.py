"""API tests for /properties/{id}/images."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from properties.enums import ImageKind
from properties.models import Property, PropertyImage


def _create_image(property_: Property, kind: str, sort_order: int = 0) -> PropertyImage:
    return PropertyImage.objects.create(
        property=property_,
        image=f"properties/sample-{sort_order}.jpg",
        kind=kind,
        sort_order=sort_order,
    )


@pytest.mark.django_db
def test_list_images(api_client: APIClient, staff: User, property_: Property) -> None:
    _create_image(property_, ImageKind.GALLERY, 0)
    _create_image(property_, ImageKind.GALLERY, 1)
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/images")
    assert response.status_code == 200
    assert response.json()["count"] == 2


@pytest.mark.django_db
def test_attach_image_by_key(api_client: APIClient, staff: User, property_: Property) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/images",
        data={
            "key": "uploaded/2026/01/file.jpg",
            "kind": ImageKind.GALLERY.value,
            "name": "Pool",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    assert PropertyImage.objects.filter(property=property_).count() == 1


@pytest.mark.django_db
def test_reorder_images(api_client: APIClient, staff: User, property_: Property) -> None:
    img_a = _create_image(property_, ImageKind.GALLERY, 0)
    img_b = _create_image(property_, ImageKind.GALLERY, 1)
    img_c = _create_image(property_, ImageKind.GALLERY, 2)
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/images:reorder",
        data={"image_ids": [img_c.pk, img_a.pk, img_b.pk]},
        format="json",
    )
    assert response.status_code == 200, response.content
    img_a.refresh_from_db()
    img_b.refresh_from_db()
    img_c.refresh_from_db()
    assert (img_c.sort_order, img_a.sort_order, img_b.sort_order) == (0, 1, 2)


@pytest.mark.django_db
def test_set_hero_promotes_and_demotes(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    hero = _create_image(property_, ImageKind.HERO, 0)
    gallery = _create_image(property_, ImageKind.GALLERY, 1)
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/images:set-hero",
        data={"image_id": gallery.pk},
        format="json",
    )
    assert response.status_code == 200, response.content
    hero.refresh_from_db()
    gallery.refresh_from_db()
    assert hero.kind == ImageKind.GALLERY.value
    assert gallery.kind == ImageKind.HERO.value
