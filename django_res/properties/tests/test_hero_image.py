import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.tests import assert_max_queries
from properties.enums import ImageKind
from properties.models import Property, PropertyImage


def _image(property_: Property, kind: ImageKind) -> PropertyImage:
    return PropertyImage.objects.create(
        property=property_,
        kind=kind,
        image=SimpleUploadedFile("img.jpg", b"x", content_type="image/jpeg"),
    )


@pytest.mark.django_db
def test_hero_image_reads_prefetched_images_without_querying(property_: Property) -> None:
    """`hero_image()` must serve from a prefetched `images` cache, not re-query.

    A `.filter()` on a prefetched reverse manager silently re-hits the DB,
    defeating any `prefetch_related("images")` a caller added to stay
    constant-query (quotation lines, bulk quote, email render). Pin that
    `hero_image()` issues zero queries once `images` is prefetched.
    """
    _image(property_, ImageKind.GALLERY)  # a non-hero to skip in Python
    _image(property_, ImageKind.HERO)

    prop = Property.objects.prefetch_related("images").get(pk=property_.pk)
    with assert_max_queries(0):
        hero = prop.hero_image()
    assert hero is not None
    assert hero.kind == ImageKind.HERO


@pytest.mark.django_db
def test_hero_image_none_when_only_inactive_or_non_hero(property_: Property) -> None:
    _image(property_, ImageKind.GALLERY)
    inactive_hero = _image(property_, ImageKind.HERO)
    inactive_hero.is_active = False
    inactive_hero.save(update_fields=["is_active"])

    prop = Property.objects.prefetch_related("images").get(pk=property_.pk)
    with assert_max_queries(0):
        assert prop.hero_image() is None
