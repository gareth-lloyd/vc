"""API tests for /organisations CRUD + :merge (GAP-046)."""

from __future__ import annotations

from typing import cast

import pytest
from rest_framework.test import APIClient

from accounts.enums import OrgStatus, OrgType
from accounts.factories import OrganisationFactory, PersonFactory
from accounts.models import Organisation, Person, User
from core.enums import StaffRole


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def admin(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="admin@example.com",
        password="x",
        role=StaffRole.ADMIN,
    )


@pytest.mark.django_db
def test_create_organisation(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/organisations",
        {"name": "Dune Travel", "org_type": OrgType.AGENCY.value, "email": "Hi@Dune.com"},
        format="json",
    )

    assert response.status_code == 201
    org = Organisation.objects.get(name="Dune Travel")
    assert org.org_type == OrgType.AGENCY.value
    # CIEmailField lowercases on save.
    assert org.email == "hi@dune.com"


@pytest.mark.django_db
def test_requires_staff(api_client: APIClient) -> None:
    response = api_client.get("/api/v1/organisations")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_list_and_retrieve(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)
    org = cast(Organisation, OrganisationFactory(name="Sandpiper"))

    listed = api_client.get("/api/v1/organisations").json()["results"]
    assert any(row["name"] == "Sandpiper" for row in listed)

    detail = api_client.get(f"/api/v1/organisations/{org.pk}").json()
    assert detail["name"] == "Sandpiper"


@pytest.mark.django_db
def test_patch_organisation(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)
    org = cast(Organisation, OrganisationFactory())

    response = api_client.patch(
        f"/api/v1/organisations/{org.pk}",
        {"status": OrgStatus.INACTIVE.value},
        format="json",
    )

    assert response.status_code == 200
    org.refresh_from_db()
    assert org.status == OrgStatus.INACTIVE.value


@pytest.mark.django_db
def test_delete_unreferenced_organisation(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)
    org = cast(Organisation, OrganisationFactory())

    response = api_client.delete(f"/api/v1/organisations/{org.pk}")

    assert response.status_code == 204
    assert not Organisation.objects.filter(pk=org.pk).exists()


@pytest.mark.django_db
def test_delete_organisation_with_agents_returns_409(api_client: APIClient, staff: User) -> None:
    """An org with agents is referenced through a PROTECT FK; deleting it must
    surface a clean 409, not an uncaught 500. (Use :merge to fold it instead.)"""
    api_client.force_login(staff)
    org = cast(Organisation, OrganisationFactory())
    PersonFactory(agency=org)

    response = api_client.delete(f"/api/v1/organisations/{org.pk}")

    assert response.status_code == 409
    assert Organisation.objects.filter(pk=org.pk).exists()


@pytest.mark.django_db
def test_filter_by_org_type_and_status(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)
    OrganisationFactory(name="Agency A", org_type=OrgType.AGENCY)
    OrganisationFactory(name="Supplier B", org_type=OrgType.SUPPLIER)
    OrganisationFactory(name="Inactive C", status=OrgStatus.INACTIVE)

    agencies = api_client.get(f"/api/v1/organisations?org_type={OrgType.AGENCY.value}").json()[
        "results"
    ]
    assert {row["name"] for row in agencies} >= {"Agency A", "Inactive C"}
    assert all(row["org_type"] == OrgType.AGENCY.value for row in agencies)

    inactive = api_client.get(f"/api/v1/organisations?status={OrgStatus.INACTIVE.value}").json()[
        "results"
    ]
    assert {row["name"] for row in inactive} == {"Inactive C"}


@pytest.mark.django_db
def test_search_by_name_and_email(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)
    OrganisationFactory(name="Dune Travel Co", email="ops@dune.com")
    OrganisationFactory(name="Sandpiper", email="hello@sandpiper.com")

    by_name = api_client.get("/api/v1/organisations?search=Dune").json()["results"]
    assert {row["name"] for row in by_name} == {"Dune Travel Co"}

    by_email = api_client.get("/api/v1/organisations?search=sandpiper.com").json()["results"]
    assert {row["name"] for row in by_email} == {"Sandpiper"}


@pytest.mark.django_db
def test_merge_repoints_agents_and_deletes_source(api_client: APIClient, admin: User) -> None:
    api_client.force_login(admin)
    source = cast(Organisation, OrganisationFactory())
    target = cast(Organisation, OrganisationFactory())
    agent = cast(Person, PersonFactory(agency=source))

    response = api_client.post(
        f"/api/v1/organisations/{source.pk}:merge",
        {"target_organisation_id": target.pk},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["id"] == target.pk
    agent.refresh_from_db()
    assert agent.agency_id == target.pk
    assert not Organisation.objects.filter(pk=source.pk).exists()


@pytest.mark.django_db
def test_merge_into_self_returns_400(api_client: APIClient, admin: User) -> None:
    api_client.force_login(admin)
    org = cast(Organisation, OrganisationFactory())

    response = api_client.post(
        f"/api/v1/organisations/{org.pk}:merge",
        {"target_organisation_id": org.pk},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "merge_invalid"


@pytest.mark.django_db
def test_merge_requires_admin(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)
    source = cast(Organisation, OrganisationFactory())
    target = cast(Organisation, OrganisationFactory())

    response = api_client.post(
        f"/api/v1/organisations/{source.pk}:merge",
        {"target_organisation_id": target.pk},
        format="json",
    )

    assert response.status_code == 403
