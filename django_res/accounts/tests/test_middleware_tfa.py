"""Tests for TfaEnforcementMiddleware (GAP-057 Unit 2).

The middleware funnels every unenrolled ``is_staff`` user into TOTP enrolment
when ``TFA_ENFORCED`` is on: it may reach only the allowlist, and every other
``/api/`` path returns 403 ``tfa_enrollment_required``. Scoped to ``/api/`` so
the SPA shell + static assets still load (the user must be able to render the
enrolment page).
"""

from __future__ import annotations

import base64

import pyotp
import pytest
from django.test import RequestFactory, override_settings
from rest_framework.test import APIClient

from accounts.enums import TfaMethod
from accounts.middleware import TfaEnforcementMiddleware
from accounts.models import User


def _basic_auth_header(email: str, password: str) -> str:
    raw = base64.b64encode(f"{email}:{password}".encode()).decode()
    return f"Basic {raw}"


# A non-allowlisted, authenticated /api endpoint used as the "arbitrary" probe.
_BLOCKED_PATH = "/api/v1/auth/sessions"


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff_user(db: None) -> User:
    return User.objects.create_user(email="staff@example.com", password="pw", is_staff=True)


@pytest.fixture
def enrolled_staff(staff_user: User) -> User:
    staff_user.tfa_method = TfaMethod.TOTP
    staff_user.tfa_secret = pyotp.random_base32()
    staff_user.save(update_fields=["tfa_method", "tfa_secret"])
    return staff_user


@pytest.fixture
def plain_user(db: None) -> User:
    return User.objects.create_user(email="viewer@example.com", password="pw", is_staff=False)


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
def test_unenrolled_staff_blocked_on_arbitrary_api_endpoint(
    api_client: APIClient, staff_user: User
) -> None:
    api_client.force_login(staff_user)

    response = api_client.get(_BLOCKED_PATH)

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "tfa_enrollment_required"
    assert body["field_errors"] == {}


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/csrf",
        "/api/v1/auth/me",
        "/api/v1/auth/permissions",
    ],
)
def test_unenrolled_staff_allowed_on_allowlist_get(
    api_client: APIClient, staff_user: User, path: str
) -> None:
    api_client.force_login(staff_user)

    response = api_client.get(path)

    assert response.status_code != 403


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
def test_unenrolled_staff_can_enroll(api_client: APIClient, staff_user: User) -> None:
    api_client.force_login(staff_user)

    response = api_client.post("/api/v1/auth/2fa:enroll", {}, format="json")

    assert response.status_code == 200
    assert response.json()["secret"]


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
def test_enrolled_staff_not_blocked(api_client: APIClient, enrolled_staff: User) -> None:
    api_client.force_login(enrolled_staff)

    response = api_client.get(_BLOCKED_PATH)

    assert response.status_code == 200


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
def test_non_staff_user_not_blocked(api_client: APIClient, plain_user: User) -> None:
    api_client.force_login(plain_user)

    response = api_client.get(_BLOCKED_PATH)

    assert response.status_code == 200


@pytest.mark.django_db
def test_flag_off_is_noop_for_unenrolled_staff(api_client: APIClient, staff_user: User) -> None:
    # No override — base TFA_ENFORCED is False.
    api_client.force_login(staff_user)

    response = api_client.get(_BLOCKED_PATH)

    assert response.status_code == 200


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
def test_non_api_path_not_blocked(staff_user: User) -> None:
    # The middleware must never touch non-/api/ paths — the SPA shell and
    # static assets must load so the user can render /enroll-2fa.
    request = RequestFactory().get("/")
    request.user = staff_user
    sentinel = object()
    middleware = TfaEnforcementMiddleware(lambda _req: sentinel)  # type: ignore[arg-type,return-value]

    assert middleware(request) is sentinel


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
def test_disable_blocked_for_staff_when_enforced(
    api_client: APIClient, enrolled_staff: User
) -> None:
    # Self-serve disable would be an enforcement bypass: an enrolled staff user
    # passes the middleware, so :disable itself must refuse while enforced.
    api_client.force_login(enrolled_staff)

    response = api_client.post("/api/v1/auth/2fa:disable")

    assert response.status_code == 403
    assert response.json()["code"] == "tfa_enrollment_required"
    enrolled_staff.refresh_from_db()
    assert enrolled_staff.tfa_method == TfaMethod.TOTP


@pytest.mark.django_db
def test_disable_allowed_when_flag_off(api_client: APIClient, enrolled_staff: User) -> None:
    api_client.force_login(enrolled_staff)

    response = api_client.post("/api/v1/auth/2fa:disable")

    assert response.status_code == 204
    enrolled_staff.refresh_from_db()
    assert enrolled_staff.tfa_method == TfaMethod.NONE


# --- Basic auth must not let staff bypass the session/2FA flow (review #1) ---


@override_settings(TFA_ENFORCED=True)
@pytest.mark.django_db
def test_staff_cannot_authenticate_via_basic_auth(api_client: APIClient, staff_user: User) -> None:
    # No session cookie — only a Basic header. The enforcement middleware sees
    # an anonymous request (session only) and passes it through; the DRF Basic
    # authenticator must then refuse the staff principal, so the endpoint is
    # never reached un-enrolled.
    staff_user.set_password("pw")
    staff_user.save(update_fields=["password"])

    response = api_client.get(
        _BLOCKED_PATH,
        headers={"Authorization": _basic_auth_header(staff_user.email, "pw")},
    )

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_non_staff_basic_auth_still_works(api_client: APIClient, plain_user: User) -> None:
    # Owner/non-staff Basic auth (the iCal calendar feed) must keep working.
    plain_user.set_password("pw")
    plain_user.save(update_fields=["password"])

    response = api_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": _basic_auth_header(plain_user.email, "pw")},
    )

    assert response.status_code == 200
    assert response.json()["email"] == plain_user.email
