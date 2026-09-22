"""The `other-information` category slug cannot be changed through the API.

The Features tab, the Zoho payload partition and the seeding stage all key on
`OTHER_INFORMATION_CATEGORY_SLUG`; the Tags admin exposes the slug as a free
text field, and a rename silently emptied all three.
"""

from __future__ import annotations

from typing import cast

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from properties.factories import FeatureCategoryFactory
from properties.models import FeatureCategory
from properties.other_information_catalog import OTHER_INFORMATION_CATEGORY_SLUG

pytestmark = pytest.mark.django_db


@pytest.fixture
def reserved(db: None) -> FeatureCategory:
    return cast(
        FeatureCategory,
        FeatureCategoryFactory(name="Other Information", slug=OTHER_INFORMATION_CATEGORY_SLUG),
    )


@pytest.fixture
def outdoor(db: None) -> FeatureCategory:
    return cast(FeatureCategory, FeatureCategoryFactory(name="Outdoor", slug="outdoor"))


def _patch(api_client: APIClient, staff: User, category: FeatureCategory, data: dict) -> object:
    api_client.force_authenticate(staff)
    return api_client.patch(f"/api/v1/feature-categories/{category.pk}", data, format="json")


def test_reserved_slug_change_is_rejected(
    api_client: APIClient, staff: User, reserved: FeatureCategory
) -> None:
    resp = _patch(api_client, staff, reserved, {"slug": "other-information-tags"})
    assert resp.status_code == 400  # type: ignore[attr-defined]
    assert "slug" in resp.json()["field_errors"]  # type: ignore[attr-defined]
    reserved.refresh_from_db()
    assert reserved.slug == OTHER_INFORMATION_CATEGORY_SLUG


def test_reserved_category_rename_keeps_slug(
    api_client: APIClient, staff: User, reserved: FeatureCategory
) -> None:
    resp = _patch(api_client, staff, reserved, {"name": "Other Information Tags"})
    assert resp.status_code == 200  # type: ignore[attr-defined]
    reserved.refresh_from_db()
    assert reserved.name == "Other Information Tags"
    assert reserved.slug == OTHER_INFORMATION_CATEGORY_SLUG


def test_reserved_slug_resubmitted_unchanged_is_accepted(
    api_client: APIClient, staff: User, reserved: FeatureCategory
) -> None:
    # The admin dialog PUTs the whole form, slug included.
    resp = _patch(api_client, staff, reserved, {"slug": OTHER_INFORMATION_CATEGORY_SLUG})
    assert resp.status_code == 200  # type: ignore[attr-defined]


def test_other_category_slug_is_editable(
    api_client: APIClient, staff: User, outdoor: FeatureCategory
) -> None:
    resp = _patch(api_client, staff, outdoor, {"slug": "outdoors"})
    assert resp.status_code == 200  # type: ignore[attr-defined]
    outdoor.refresh_from_db()
    assert outdoor.slug == "outdoors"
