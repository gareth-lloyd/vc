"""Hard-deleting an image row must release its stored file (local or S3)."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from properties.enums import ImageKind
from properties.models import Collection, Property, PropertyImage


def _upload(name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"file-bytes", content_type="image/jpeg")


@pytest.mark.django_db
def test_property_image_delete_removes_stored_file(property_: Property) -> None:
    image = PropertyImage.objects.create(
        property=property_,
        image=_upload("pool.jpg"),
        kind=ImageKind.GALLERY,
    )
    storage, name = image.image.storage, image.image.name
    assert name is not None
    assert storage.exists(name)

    image.delete()

    assert not storage.exists(name)


@pytest.mark.django_db
def test_property_image_delete_tolerates_missing_file(property_: Property) -> None:
    # Legacy rows hold a key with no backing file until the binary import runs.
    image = PropertyImage.objects.create(
        property=property_,
        image="properties/legacy/nonexistent.jpg",
        kind=ImageKind.GALLERY,
    )
    image.delete()  # must not raise
    assert not PropertyImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_collection_delete_removes_cover_file() -> None:
    collection = Collection.objects.create(
        name="Beachfront",
        slug="beachfront",
        cover_image=_upload("cover.jpg"),
    )
    storage, name = collection.cover_image.storage, collection.cover_image.name
    assert name is not None
    assert storage.exists(name)

    collection.delete()

    assert not storage.exists(name)
