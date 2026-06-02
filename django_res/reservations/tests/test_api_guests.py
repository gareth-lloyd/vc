"""API tests for /guests CRUD + :merge + :anonymize."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from reservations.enums import GuestStatus
from reservations.models import Guest


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def admin(db: None) -> User:
    return User.objects.create_user(email="admin@example.com", password="x", role=StaffRole.ADMIN)


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        email="staff@example.com", password="x", role=StaffRole.RESERVATIONS
    )


@pytest.mark.django_db
def test_create_guest(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/guests",
        {
            "first_name": "Alan",
            "last_name": "Turing",
            "email": "alan@example.com",
        },
        format="json",
    )

    assert response.status_code == 201
    assert Guest.objects.filter(email="alan@example.com").exists()


@pytest.mark.django_db
def test_list_guests(api_client: APIClient, staff: User, guest: Guest) -> None:
    api_client.force_login(staff)

    response = api_client.get("/api/v1/guests")

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["results"]}
    assert guest.pk in ids


@pytest.mark.django_db
def test_patch_guest(api_client: APIClient, staff: User, guest: Guest) -> None:
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/guests/{guest.pk}",
        {"phone": "+44 7700 900000"},
        format="json",
    )

    assert response.status_code == 200
    guest.refresh_from_db()
    assert guest.phone == "+44 7700 900000"


@pytest.mark.django_db
def test_merge_requires_admin(api_client: APIClient, staff: User, guest: Guest) -> None:
    target = Guest.objects.create(first_name="Target", last_name="Guest", email="t@x.com")
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/guests/{guest.pk}:merge",
        {"target_guest_id": target.pk},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_merge_hard_deletes_source(api_client: APIClient, admin: User, guest: Guest) -> None:
    target = Guest.objects.create(first_name="Target", last_name="Guest", email="t@x.com")
    api_client.force_login(admin)

    response = api_client.post(
        f"/api/v1/guests/{guest.pk}:merge",
        {"target_guest_id": target.pk},
        format="json",
    )

    assert response.status_code == 200
    assert not Guest.objects.filter(pk=guest.pk).exists()
    assert Guest.objects.filter(pk=target.pk).exists()


@pytest.mark.django_db
def test_merge_into_self_returns_400(api_client: APIClient, admin: User, guest: Guest) -> None:
    api_client.force_login(admin)

    response = api_client.post(
        f"/api/v1/guests/{guest.pk}:merge",
        {"target_guest_id": guest.pk},
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_anonymize_redacts_pii(api_client: APIClient, admin: User, guest: Guest) -> None:
    api_client.force_login(admin)

    response = api_client.post(f"/api/v1/guests/{guest.pk}:anonymize")

    assert response.status_code == 200
    guest.refresh_from_db()
    assert guest.status == GuestStatus.ANONYMIZED.value
    assert guest.first_name == "[REDACTED]"


@pytest.mark.django_db
def test_anonymize_requires_admin(api_client: APIClient, staff: User, guest: Guest) -> None:
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/guests/{guest.pk}:anonymize")

    assert response.status_code == 403
