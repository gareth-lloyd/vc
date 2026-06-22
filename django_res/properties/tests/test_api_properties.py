"""API tests for /properties — CRUD + lifecycle actions."""

from __future__ import annotations

from typing import cast

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from accounts.models import User
from core.tests import assert_max_queries
from properties import factories
from properties.enums import ImageKind, PropertyStatus
from properties.models import (
    Feature,
    FeatureCategory,
    Property,
    PropertyCalendarFeed,
    PropertyCategory,
    PropertyFeature,
    PropertyGroup,
    PropertyImage,
    PropertyLocation,
    PropertySettings,
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
def test_duplicate_clones_feature_links(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """`duplicate()` copies feature links via `features.set()`. Guard that the
    GAP-022 through-model swap (`PropertyFeature`) keeps `.set()` working — it
    relies on `sort_order` having a DB default; a future required field would
    break the copy silently without this assertion."""
    feature = cast(Feature, factories.FeatureFactory())
    property_.features.set([feature])

    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/properties/{property_.pk}:duplicate", format="json")
    assert response.status_code == 201, response.content

    clone = Property.objects.get(pk=response.json()["id"])
    assert list(clone.features.values_list("pk", flat=True)) == [feature.pk]


# --- GAP-022: per-villa feature display order (sort_order) -------------------


def _shared_category() -> FeatureCategory:
    return cast(FeatureCategory, factories.FeatureCategoryFactory(slug="gap022-shared-cat"))


def _named_feature(name: str, slug: str, category: FeatureCategory) -> Feature:
    return cast(Feature, factories.FeatureFactory(name=name, slug=slug, category=category))


@pytest.mark.django_db
def test_create_property_persists_feature_order(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    group: PropertyGroup,
    region: Region,
) -> None:
    """The order of `features` on create becomes the per-villa `sort_order`."""
    cat = _shared_category()
    a = _named_feature("Apple", "feat-a", cat)
    b = _named_feature("Mango", "feat-b", cat)
    c = _named_feature("Zebra", "feat-c", cat)

    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/properties",
        data={
            "name": "Ordered Villa",
            "display_name": "Ordered Villa",
            "slug": "ordered-villa",
            "category": category.pk,
            "group": group.pk,
            "region": region.pk,
            "features": [c.pk, a.pk, b.pk],
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    prop_id = response.json()["id"]

    links = PropertyFeature.objects.filter(property_id=prop_id).order_by("sort_order")
    assert [(link.feature_id, link.sort_order) for link in links] == [
        (c.pk, 0),
        (a.pk, 1),
        (b.pk, 2),
    ]
    # The create response reflects the persisted per-villa order.
    assert response.json()["feature_ids"] == [c.pk, a.pk, b.pk]


@pytest.mark.django_db
def test_detail_feature_ids_follow_sort_order_not_global_rank(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """`feature_ids` reflects per-villa `sort_order`, NOT `Feature._meta.ordering`
    (category, sort_order, name). With a shared category the global rank is by
    name (Apple, Mango, Zebra); the per-villa order here is the reverse-ish
    [Zebra, Apple, Mango], so a passing assertion proves the through is walked."""
    cat = _shared_category()
    a = _named_feature("Apple", "feat-a", cat)
    b = _named_feature("Mango", "feat-b", cat)
    c = _named_feature("Zebra", "feat-c", cat)
    PropertyFeature.objects.create(property=property_, feature=c, sort_order=0)
    PropertyFeature.objects.create(property=property_, feature=a, sort_order=1)
    PropertyFeature.objects.create(property=property_, feature=b, sort_order=2)

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}")
    assert response.status_code == 200, response.content
    assert response.json()["feature_ids"] == [c.pk, a.pk, b.pk]


@pytest.mark.django_db
def test_patch_features_adds_and_removes_links(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    cat = _shared_category()
    a = _named_feature("Apple", "feat-a", cat)
    b = _named_feature("Mango", "feat-b", cat)
    c = _named_feature("Zebra", "feat-c", cat)
    PropertyFeature.objects.create(property=property_, feature=a, sort_order=0)
    PropertyFeature.objects.create(property=property_, feature=b, sort_order=1)

    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}",
        data={"features": [b.pk, c.pk]},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["feature_ids"] == [b.pk, c.pk]

    links = {pf.feature_id: pf.sort_order for pf in property_.feature_links.all()}
    assert links == {b.pk: 0, c.pk: 1}  # a removed, c added, b re-positioned
    assert not PropertyFeature.objects.filter(property=property_, feature=a).exists()


@pytest.mark.django_db
def test_partial_patch_without_features_leaves_links(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """A PATCH that omits `features` must not touch the existing links."""
    cat = _shared_category()
    a = _named_feature("Apple", "feat-a", cat)
    b = _named_feature("Mango", "feat-b", cat)
    PropertyFeature.objects.create(property=property_, feature=a, sort_order=0)
    PropertyFeature.objects.create(property=property_, feature=b, sort_order=1)

    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}",
        data={"display_name": "Renamed Only"},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["feature_ids"] == [a.pk, b.pk]
    assert PropertyFeature.objects.filter(property=property_).count() == 2


@pytest.mark.django_db
def test_patch_reorder_writes_only_moved_links(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """A pure reorder must issue an UPDATE only for the rows that actually moved.
    The diff-writer's `sort_order != position` guard is what skips the unchanged
    row — and only a real query-count check proves it (the audit layer diffs
    independently, so an AuditLog assertion would pass even without the guard)."""
    cat = _shared_category()
    a = _named_feature("Apple", "feat-a", cat)
    b = _named_feature("Mango", "feat-b", cat)
    c = _named_feature("Zebra", "feat-c", cat)
    PropertyFeature.objects.create(property=property_, feature=a, sort_order=0)
    PropertyFeature.objects.create(property=property_, feature=b, sort_order=1)
    PropertyFeature.objects.create(property=property_, feature=c, sort_order=2)

    api_client.force_login(staff)
    # Swap b and c; a stays at position 0 and must NOT be re-saved.
    with CaptureQueriesContext(connection) as captured:
        response = api_client.patch(
            f"/api/v1/properties/{property_.pk}",
            data={"features": [a.pk, c.pk, b.pk]},
            format="json",
        )
    assert response.status_code == 200, response.content
    assert response.json()["feature_ids"] == [a.pk, c.pk, b.pk]

    link_updates = [
        q["sql"]
        for q in captured.captured_queries
        if q["sql"].startswith('UPDATE "properties_property_features"')
    ]
    # b and c moved → exactly two UPDATEs; a was guarded out. Drop the guard and
    # this becomes three.
    assert len(link_updates) == 2, link_updates


@pytest.mark.django_db
def test_detail_feature_ids_query_count_is_constant(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """`feature_ids` must cost the same number of queries no matter how many
    features a property has — the regression guard against `get_feature_ids`
    growing an N+1 (e.g. by walking `link.feature` without `select_related`)."""
    cat = _shared_category()
    api_client.force_login(staff)

    PropertyFeature.objects.create(
        property=property_, feature=_named_feature("One", "feat-one", cat), sort_order=0
    )
    api_client.get(f"/api/v1/properties/{property_.pk}")  # warm content-type caches
    with CaptureQueriesContext(connection) as one_feature:
        api_client.get(f"/api/v1/properties/{property_.pk}")

    for i in range(5):
        PropertyFeature.objects.create(
            property=property_,
            feature=_named_feature(f"More {i}", f"feat-m-{i}", cat),
            sort_order=i + 1,
        )
    with CaptureQueriesContext(connection) as six_features:
        response = api_client.get(f"/api/v1/properties/{property_.pk}")

    assert response.status_code == 200, response.content
    assert len(response.json()["feature_ids"]) == 6
    assert len(six_features.captured_queries) == len(one_feature.captured_queries)


@pytest.mark.django_db
def test_import_from_zoho_returns_501(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/properties/{property_.pk}:import-from-zoho")
    assert response.status_code == 501
    assert response.json()["code"] == "not_implemented"


# --- GAP-034: calendar-source indicators on property list/detail ---------------


def _list_row(payload: dict, property_id: int) -> dict:
    """Pluck a single property's row out of the paginated list payload."""
    rows = [row for row in payload["results"] if row["id"] == property_id]
    assert len(rows) == 1, f"expected exactly one row for property {property_id}"
    return rows[0]


@pytest.mark.django_db
def test_list_has_active_ical_feed_true_with_active_feed(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """An active `PropertyCalendarFeed` flips the list flag to true."""
    PropertyCalendarFeed.objects.create(
        property=property_, url="https://example.test/ical/a.ics", is_active=True
    )
    api_client.force_login(staff)
    response = api_client.get("/api/v1/properties")
    assert response.status_code == 200, response.content
    assert _list_row(response.json(), property_.pk)["has_active_ical_feed"] is True


@pytest.mark.django_db
def test_list_has_active_ical_feed_false_without_feed(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """No feed → flag is false (never absent/null)."""
    api_client.force_login(staff)
    response = api_client.get("/api/v1/properties")
    assert response.status_code == 200, response.content
    assert _list_row(response.json(), property_.pk)["has_active_ical_feed"] is False


@pytest.mark.django_db
def test_has_active_ical_feed_false_with_only_inactive_feed(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """An inactive feed must not count — only `is_active=True` feeds flip it."""
    PropertyCalendarFeed.objects.create(
        property=property_, url="https://example.test/ical/off.ics", is_active=False
    )
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}")
    assert response.status_code == 200, response.content
    assert response.json()["has_active_ical_feed"] is False


@pytest.mark.django_db
def test_detail_has_active_ical_feed_true_with_active_feed(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    PropertyCalendarFeed.objects.create(
        property=property_, url="https://example.test/ical/d.ics", is_active=True
    )
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}")
    assert response.status_code == 200, response.content
    assert response.json()["has_active_ical_feed"] is True


@pytest.mark.django_db
def test_feed_url_never_serialized_in_property_payloads(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """The feed `url` is a secret capability URL — it must never appear in any
    property payload (list or detail), only the boolean flag (GAP-011/GAP-034)."""
    secret = "https://secret.example.test/ical/SUPERSECRETTOKEN.ics"
    PropertyCalendarFeed.objects.create(property=property_, url=secret, is_active=True)
    api_client.force_login(staff)

    list_response = api_client.get("/api/v1/properties")
    assert secret not in list_response.content.decode()
    detail_response = api_client.get(f"/api/v1/properties/{property_.pk}")
    assert secret not in detail_response.content.decode()
    # And no feed/url-shaped keys leak into the row at all.
    row = _list_row(list_response.json(), property_.pk)
    assert "url" not in row
    assert "calendar_feeds" not in row


@pytest.mark.django_db
def test_calendar_url_surfaced_on_list_and_detail(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """`calendar_url` from `PropertySettings` is surfaced on both shapes."""
    url = "https://owner.example.com/calendar"
    PropertySettings.objects.create(property=property_, calendar_url=url)
    api_client.force_login(staff)

    list_response = api_client.get("/api/v1/properties")
    assert _list_row(list_response.json(), property_.pk)["calendar_url"] == url
    detail_response = api_client.get(f"/api/v1/properties/{property_.pk}")
    assert detail_response.json()["calendar_url"] == url


@pytest.mark.django_db
def test_calendar_url_null_when_no_settings_row(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """A settings-less property (the `property_` fixture) reports null, not a 500
    — the `ObjectDoesNotExist`-guarded read path."""
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}")
    assert response.status_code == 200, response.content
    assert response.json()["calendar_url"] is None


@pytest.mark.django_db
def test_property_with_both_feed_and_calendar_url(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """Precedence is a FE concern: the BE exposes BOTH the flag and the url when a
    property has an active feed and a `calendar_url`."""
    PropertyCalendarFeed.objects.create(
        property=property_, url="https://example.test/ical/both.ics", is_active=True
    )
    PropertySettings.objects.create(
        property=property_, calendar_url="https://owner.example.com/calendar"
    )
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}")
    body = response.json()
    assert body["has_active_ical_feed"] is True
    assert body["calendar_url"] == "https://owner.example.com/calendar"


@pytest.mark.django_db
def test_create_response_includes_flag_via_fallback(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    group: PropertyGroup,
    region: Region,
) -> None:
    """`create` serializes a fresh, non-annotated instance — the SMF must fall
    back to `.exists()` instead of crashing on the missing annotation."""
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
    assert response.json()["has_active_ical_feed"] is False
    assert response.json()["calendar_url"] is None


@pytest.mark.django_db
def test_duplicate_response_includes_flag_via_fallback(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """`duplicate` also returns a fresh, non-annotated clone — same fallback."""
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/properties/{property_.pk}:duplicate", format="json")
    assert response.status_code == 201, response.content
    assert response.json()["has_active_ical_feed"] is False


@pytest.mark.django_db
def test_list_query_count_constant_with_feeds_and_settings(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    group: PropertyGroup,
    region: Region,
) -> None:
    """Surfacing the flag (a scalar `Exists`) and `calendar_url`
    (`select_related("settings")`) must add no per-row query — the count stays
    flat as the property set grows. Guards against an accidental N+1."""

    def _make(n_start: int, n: int) -> None:
        for idx in range(n_start, n_start + n):
            prop = Property.objects.create(
                name=f"QC Villa {idx}",
                display_name=f"QC Villa {idx}",
                slug=f"qc-villa-{idx}",
                category=category,
                group=group,
                region=region,
            )
            PropertySettings.objects.create(
                property=prop, calendar_url=f"https://owner.example.com/{idx}"
            )
            PropertyCalendarFeed.objects.create(
                property=prop, url=f"https://example.test/ical/qc-{idx}.ics", is_active=True
            )

    _make(0, 5)
    api_client.force_login(staff)
    api_client.get("/api/v1/properties")  # warm caches
    # Fixed ceiling (catches a constant baseline regression) AND scale-invariance
    # (the larger set must stay within the small-set count → no per-row N+1).
    with assert_max_queries(15) as small:
        response = api_client.get("/api/v1/properties")
    assert response.status_code == 200, response.content
    baseline = len(small.captured_queries)

    _make(5, 10)
    with assert_max_queries(baseline) as large:
        response = api_client.get("/api/v1/properties")
    assert response.status_code == 200, response.content
    assert len(large.captured_queries) <= baseline
