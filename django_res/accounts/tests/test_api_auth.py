"""API tests for /auth/* endpoints."""

from __future__ import annotations

import pyotp
import pytest
from rest_framework.test import APIClient

from accounts.enums import TfaMethod
from accounts.models import User


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def password() -> str:
    return "correct horse battery staple"


@pytest.fixture
def user(db: None, password: str) -> User:
    return User.objects.create_user(
        email="ops@example.com",
        password=password,
        first_name="Ops",
        last_name="User",
    )


@pytest.mark.django_db
def test_login_returns_user_when_tfa_disabled(
    api_client: APIClient, user: User, password: str
) -> None:
    response = api_client.post(
        "/api/v1/auth/login",
        {"email": user.email, "password": password},
        format="json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tfa_required"] is False
    assert body["user"]["email"] == user.email


@pytest.mark.django_db
def test_login_with_wrong_password_returns_401(api_client: APIClient, user: User) -> None:
    response = api_client.post(
        "/api/v1/auth/login",
        {"email": user.email, "password": "nope"},
        format="json",
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


@pytest.mark.django_db
def test_logout_clears_session(api_client: APIClient, user: User) -> None:
    api_client.force_login(user)

    response = api_client.post("/api/v1/auth/logout")

    assert response.status_code == 204


@pytest.mark.django_db
def test_me_returns_current_user(api_client: APIClient, user: User) -> None:
    api_client.force_login(user)

    response = api_client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == user.email


@pytest.mark.django_db
def test_me_requires_auth(api_client: APIClient) -> None:
    response = api_client.get("/api/v1/auth/me")

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_me_exposes_preferred_language_default(api_client: APIClient, user: User) -> None:
    api_client.force_login(user)

    response = api_client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["preferred_language"] == "en"


@pytest.mark.django_db
def test_me_patch_updates_preferred_language(api_client: APIClient, user: User) -> None:
    api_client.force_login(user)

    response = api_client.patch(
        "/api/v1/auth/me",
        {"preferred_language": "es"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["preferred_language"] == "es"
    user.refresh_from_db()
    assert user.preferred_language == "es"


@pytest.mark.django_db
def test_password_change_updates_password(api_client: APIClient, user: User, password: str) -> None:
    api_client.force_login(user)

    response = api_client.post(
        "/api/v1/auth/me/password",
        {"current_password": password, "new_password": "newsecretpw"},
        format="json",
    )

    assert response.status_code == 204
    user.refresh_from_db()
    assert user.check_password("newsecretpw")


@pytest.mark.django_db
def test_password_change_rejects_wrong_current(api_client: APIClient, user: User) -> None:
    api_client.force_login(user)

    response = api_client.post(
        "/api/v1/auth/me/password",
        {"current_password": "wrong", "new_password": "newsecretpw"},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_credentials"


@pytest.mark.django_db
def test_permissions_endpoint_returns_role(api_client: APIClient, user: User) -> None:
    api_client.force_login(user)

    response = api_client.get("/api/v1/auth/permissions")

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == user.role
    assert isinstance(body["permissions"], list)


@pytest.mark.django_db
def test_tfa_enroll_returns_secret(api_client: APIClient, user: User) -> None:
    api_client.force_login(user)

    response = api_client.post("/api/v1/auth/2fa:enroll", {}, format="json")

    assert response.status_code == 200
    body = response.json()
    assert body["secret"]
    assert body["provisioning_uri"].startswith("otpauth://")
    assert len(body["recovery_codes"]) == 10


@pytest.mark.django_db
def test_tfa_enroll_then_confirm_with_code(api_client: APIClient, user: User) -> None:
    api_client.force_login(user)
    api_client.post("/api/v1/auth/2fa:enroll", {}, format="json")
    user.refresh_from_db()
    code = pyotp.TOTP(user.tfa_secret).now()

    response = api_client.post("/api/v1/auth/2fa:enroll", {"code": code}, format="json")

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.tfa_method == TfaMethod.TOTP


@pytest.mark.django_db
def test_tfa_disable_clears_state(api_client: APIClient, user: User) -> None:
    user.tfa_method = TfaMethod.TOTP
    user.tfa_secret = pyotp.random_base32()
    user.save(update_fields=["tfa_method", "tfa_secret"])
    api_client.force_login(user)

    response = api_client.post("/api/v1/auth/2fa:disable")

    assert response.status_code == 204
    user.refresh_from_db()
    assert user.tfa_method == TfaMethod.NONE
    assert user.tfa_secret == ""


@pytest.mark.django_db
def test_magic_link_endpoints_return_501(api_client: APIClient) -> None:
    response = api_client.post(
        "/api/v1/auth/magic-link:request", {"email": "x@y.com"}, format="json"
    )

    assert response.status_code == 501
    assert response.json()["code"] == "not_implemented"


@pytest.mark.django_db
def test_password_reset_request_returns_501(api_client: APIClient) -> None:
    response = api_client.post(
        "/api/v1/auth/password-reset:request",
        {"email": "x@y.com"},
        format="json",
    )

    assert response.status_code == 501
