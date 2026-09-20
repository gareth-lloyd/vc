"""API tests for /properties/{id}/descriptions."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from core.models import AuditLog
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
@pytest.mark.parametrize(
    ("slug", "section"),
    [
        ("internal-notes", DescriptionSection.INTERNAL_NOTES),
        # GAP-091: Features-tab prose + GAP-092's property-level rooms blurb.
        ("other-information", DescriptionSection.OTHER_INFORMATION),
        ("rooms", DescriptionSection.ROOMS),
        # GAP-090: the legacy sub/para block set.
        ("web-des-1", DescriptionSection.WEB_DES_1),
        ("interior-para", DescriptionSection.INTERIOR_PARA),
        ("location-sub", DescriptionSection.LOCATION_SUB),
    ],
)
def test_hyphenated_sections_round_trip(
    api_client: APIClient,
    staff: User,
    property_: Property,
    slug: str,
    section: DescriptionSection,
) -> None:
    """Multi-word sections are first-class, reachable via their `-` slug."""
    api_client.force_login(staff)
    url = f"/api/v1/properties/{property_.pk}/descriptions/{slug}"

    created = api_client.put(url, data={"body": "Owner is difficult"}, format="json")
    assert created.status_code == 201, created.content
    assert created.json()["section"] == section.value

    fetched = api_client.get(url)
    assert fetched.status_code == 200
    assert fetched.json()["body"] == "Owner is difficult"

    removed = api_client.delete(url)
    assert removed.status_code == 204
    assert not PropertyDescription.objects.filter(property=property_, section=section).exists()


@pytest.mark.django_db
def test_put_without_body_returns_400(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """A body-less PUT must 400, not silently wipe the section.

    The view previously read `request.data.get("body", "")` directly, so a
    malformed request blanked existing copy.
    """
    PropertyDescription.objects.create(
        property=property_,
        section=DescriptionSection.OVERVIEW,
        body="Hard-won copy",
    )
    api_client.force_login(staff)
    response = api_client.put(
        f"/api/v1/properties/{property_.pk}/descriptions/overview",
        data={},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert (
        PropertyDescription.objects.get(
            property=property_, section=DescriptionSection.OVERVIEW
        ).body
        == "Hard-won copy"
    )


@pytest.mark.django_db
def test_put_records_the_editing_user(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """An edit re-attributes `updated_by`.

    `update_or_create` saves with `update_fields` covering only `defaults` plus
    auto_now columns, so the `updated_by` assigned by
    `core.signals.populate_user_fields` was silently dropped and every edit kept
    the original author — actively misleading for staff-only notes.
    """
    editor = User.objects.create_user(
        email="editor@test.com", password="x", is_staff=True, role=StaffRole.RESERVATIONS
    )
    api_client.force_login(staff)
    url = f"/api/v1/properties/{property_.pk}/descriptions/internal-notes"
    assert api_client.put(url, data={"body": "First"}, format="json").status_code == 201

    api_client.force_login(editor)
    assert api_client.put(url, data={"body": "Second"}, format="json").status_code == 200

    row = PropertyDescription.objects.get(
        property=property_, section=DescriptionSection.INTERNAL_NOTES
    )
    assert row.body == "Second"
    assert row.created_by_id == staff.pk
    assert row.updated_by_id == editor.pk


@pytest.mark.django_db
def test_put_accepts_blank_body(api_client: APIClient, staff: User, property_: Property) -> None:
    """An explicit empty string is a legitimate "clear this section"."""
    PropertyDescription.objects.create(
        property=property_,
        section=DescriptionSection.OVERVIEW,
        body="Old",
    )
    api_client.force_login(staff)
    response = api_client.put(
        f"/api/v1/properties/{property_.pk}/descriptions/overview",
        data={"body": ""},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["body"] == ""


@pytest.mark.django_db
def test_delete_leaves_an_audit_tombstone(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """Clearing a section hard-deletes the row, so it must leave a tombstone
    naming what vanished (FG-017) — staff notes are the whole reason the
    section exists, and "no soft delete" means the row itself is gone."""
    row = PropertyDescription.objects.create(
        property=property_,
        section=DescriptionSection.INTERNAL_NOTES,
        body="Owner disputes the damage charge.",
    )
    api_client.force_login(staff)
    assert (
        api_client.delete(
            f"/api/v1/properties/{property_.pk}/descriptions/internal-notes"
        ).status_code
        == 204
    )

    ct = ContentType.objects.get_for_model(PropertyDescription)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(row.pk))
    assert [r for r in rows if r.field_diffs.get("__deleted__")], (
        "expected a __deleted__ tombstone row for the cleared description"
    )


@pytest.mark.django_db
# `villa-info` was retired by GAP-091 (migration 0007 renamed its rows);
# `web-description`, `location` and `further-info` by GAP-090 (0010).
@pytest.mark.parametrize(
    "slug", ["garbage-section", "villa-info", "web-description", "location", "further-info"]
)
def test_unknown_section_returns_404(
    api_client: APIClient, staff: User, property_: Property, slug: str
) -> None:
    api_client.force_login(staff)
    response = api_client.put(
        f"/api/v1/properties/{property_.pk}/descriptions/{slug}",
        data={"body": "X"},
        format="json",
    )
    assert response.status_code == 404
