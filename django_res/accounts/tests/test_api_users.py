"""API tests for /users — admin CRUD + action endpoints."""

from __future__ import annotations

import pyotp
import pytest
from rest_framework.test import APIClient

from accounts.enums import TfaMethod
from accounts.models import User
from core.enums import StaffRole


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def admin(db: None) -> User:
    return User.objects.create_user(
        email="admin@example.com",
        password="x",
        role=StaffRole.ADMIN,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        email="viewer@example.com",
        password="x",
        role=StaffRole.VIEWER,
    )


@pytest.mark.django_db
def test_admin_can_list_users(api_client: APIClient, admin: User, viewer: User) -> None:
    api_client.force_login(admin)

    response = api_client.get("/api/v1/users")

    assert response.status_code == 200
    emails = {row["email"] for row in response.json()["results"]}
    assert {admin.email, viewer.email} <= emails


@pytest.mark.django_db
def test_admin_can_create_user(api_client: APIClient, admin: User) -> None:
    api_client.force_login(admin)

    response = api_client.post(
        "/api/v1/users",
        {
            "email": "new@example.com",
            "password": "passw0rdpassw0rd",
            "role": "reservations",
            "first_name": "New",
            "last_name": "Hire",
        },
        format="json",
    )

    assert response.status_code == 201
    assert User.objects.filter(email="new@example.com").exists()


@pytest.mark.django_db
def test_viewer_cannot_create_user(api_client: APIClient, viewer: User) -> None:
    api_client.force_login(viewer)

    response = api_client.post(
        "/api/v1/users",
        {"email": "x@y.com", "password": "passw0rdpassw0rd"},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_can_patch_user(api_client: APIClient, admin: User, viewer: User) -> None:
    api_client.force_login(admin)

    response = api_client.patch(
        f"/api/v1/users/{viewer.pk}",
        {"first_name": "Updated"},
        format="json",
    )

    assert response.status_code == 200
    viewer.refresh_from_db()
    assert viewer.first_name == "Updated"


@pytest.mark.django_db
def test_destroy_deactivates_user(api_client: APIClient, admin: User, viewer: User) -> None:
    api_client.force_login(admin)

    response = api_client.delete(f"/api/v1/users/{viewer.pk}")

    assert response.status_code == 204
    viewer.refresh_from_db()
    assert viewer.is_active is False


@pytest.mark.django_db
def test_activate_reactivates_user(api_client: APIClient, admin: User, viewer: User) -> None:
    viewer.is_active = False
    viewer.save(update_fields=["is_active"])
    api_client.force_login(admin)

    response = api_client.post(f"/api/v1/users/{viewer.pk}:activate")

    assert response.status_code == 200
    viewer.refresh_from_db()
    assert viewer.is_active is True


@pytest.mark.django_db
def test_reset_tfa_clears_state(api_client: APIClient, admin: User, viewer: User) -> None:
    viewer.tfa_method = TfaMethod.TOTP
    viewer.tfa_secret = pyotp.random_base32()
    viewer.save(update_fields=["tfa_method", "tfa_secret"])
    api_client.force_login(admin)

    response = api_client.post(f"/api/v1/users/{viewer.pk}:reset-2fa")

    assert response.status_code == 200
    viewer.refresh_from_db()
    assert viewer.tfa_method == TfaMethod.NONE
    assert viewer.tfa_secret == ""


@pytest.mark.django_db
def test_reset_password_returns_501(api_client: APIClient, admin: User, viewer: User) -> None:
    api_client.force_login(admin)

    response = api_client.post(f"/api/v1/users/{viewer.pk}:reset-password")

    assert response.status_code == 501


@pytest.mark.django_db
def test_role_list(api_client: APIClient, viewer: User) -> None:
    api_client.force_login(viewer)

    response = api_client.get("/api/v1/roles")

    assert response.status_code == 200
    values = {row["value"] for row in response.json()}
    assert {"admin", "reservations", "accounts", "viewer"} == values
