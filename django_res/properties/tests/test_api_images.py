"""API tests for /properties/{id}/images."""

from __future__ import annotations

import io
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
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


def _png_upload(name: str = "pool.png", size: tuple[int, int] = (1, 1)) -> SimpleUploadedFile:
    buf = io.BytesIO()
    Image.new("RGB", size).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@pytest.mark.django_db
def test_list_images(api_client: APIClient, staff: User, property_: Property) -> None:
    _create_image(property_, ImageKind.GALLERY, 0)
    _create_image(property_, ImageKind.GALLERY, 1)
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/images")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["results"][0]["image_url"].endswith("properties/sample-0.jpg")


@pytest.mark.django_db
def test_upload_image_multipart(api_client: APIClient, staff: User, property_: Property) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/images",
        data={
            "image": _png_upload(),
            "kind": ImageKind.GALLERY.value,
            "name": "Pool",
        },
        format="multipart",
    )
    assert response.status_code == 201, response.content
    image = PropertyImage.objects.get(property=property_)
    assert image.image.name is not None
    assert image.image.storage.exists(image.image.name)
    assert response.json()["image_url"] == image.image.url


@pytest.mark.django_db
def test_upload_rejects_non_image(api_client: APIClient, staff: User, property_: Property) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/images",
        data={
            "image": SimpleUploadedFile("notes.txt", b"not an image", content_type="text/plain"),
            "kind": ImageKind.GALLERY.value,
        },
        format="multipart",
    )
    assert response.status_code == 400
    assert PropertyImage.objects.filter(property=property_).count() == 0


@pytest.mark.django_db
def test_upload_rejects_oversized_image(
    api_client: APIClient,
    staff: User,
    property_: Property,
    settings: Any,
) -> None:
    settings.MAX_IMAGE_BYTES = 10  # any real PNG is bigger than this
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/images",
        data={
            "image": _png_upload(),
            "kind": ImageKind.GALLERY.value,
        },
        format="multipart",
    )
    assert response.status_code == 400
    assert "image" in response.json()["field_errors"]
    assert PropertyImage.objects.filter(property=property_).count() == 0


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
