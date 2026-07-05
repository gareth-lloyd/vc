"""API tests for /auth/* endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyotp
import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.enums import TfaMethod
from accounts.models import User

if TYPE_CHECKING:
    from comms.models import SmtpProfile


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


def _enrol_totp(user: User) -> None:
    user.tfa_method = TfaMethod.TOTP
    user.tfa_secret = pyotp.random_base32()
    user.save(update_fields=["tfa_method", "tfa_secret"])


@pytest.mark.django_db
def test_login_challenges_enrolled_user_when_challenge_on(
    api_client: APIClient, user: User, password: str
) -> None:
    """Fail-closed default (base/prod): an enrolled user gets an OTP challenge
    instead of a completed session."""
    _enrol_totp(user)

    response = api_client.post(
        "/api/v1/auth/login",
        {"email": user.email, "password": password},
        format="json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tfa_required"] is True
    assert body["challenge_token"]
    assert "user" not in body


@pytest.mark.django_db
@override_settings(TFA_LOGIN_CHALLENGE=False)
def test_login_skips_challenge_for_enrolled_user_in_dev(
    api_client: APIClient, user: User, password: str
) -> None:
    """With TFA_LOGIN_CHALLENGE off (dev), an enrolled user logs in directly —
    no OTP step, so Playwright and the pre-enrolled dev superuser breeze in."""
    _enrol_totp(user)

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


def test_csrf_prime_sets_cookie_for_anonymous(api_client: APIClient) -> None:
    response = api_client.get("/api/v1/auth/csrf")

    assert response.status_code == 204
    assert "csrftoken" in response.cookies


def test_csrf_prime_then_login_succeeds_with_enforced_csrf(db: None, password: str) -> None:
    """A fresh browser that primes via /auth/csrf can log in first try.

    `enforce_csrf_checks=True` makes the test client behave like a real
    browser against CsrfViewMiddleware — without the prime, the first
    login POST 403s (the historical "log in twice" bug).
    """
    user = User.objects.create_user(
        email="fresh@example.com",
        password=password,
        first_name="Fresh",
        last_name="Browser",
    )
    client = APIClient(enforce_csrf_checks=True)

    prime = client.get("/api/v1/auth/csrf")
    token = prime.cookies["csrftoken"].value

    response = client.post(
        "/api/v1/auth/login",
        {"email": user.email, "password": password},
        format="json",
        headers={"X-CSRFToken": token},
    )

    assert response.status_code == 200


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


@pytest.fixture
def system_smtp_profile(db: None) -> SmtpProfile:
    from comms.enums import SmtpScope
    from comms.models import SmtpProfile

    return SmtpProfile.objects.create(
        name="System",
        scope=SmtpScope.SYSTEM,
        owner=None,
        host="smtp.example.com",
        port=587,
        username="system",
        encrypted_password="systempw",
        from_email="noreply@example.com",
    )


# Password-reset dispatch is deferred to transaction.on_commit; run the hook
# immediately so the email/log assertions observe the send.
@pytest.mark.usefixtures("run_on_commit_immediately")
@pytest.mark.django_db
def test_password_reset_request_sends_email_and_persists_log(
    api_client: APIClient,
    user: User,
    system_smtp_profile: SmtpProfile,
) -> None:
    from typing import cast

    from django.core import mail
    from django.core.mail import EmailMultiAlternatives

    from comms.models import EmailLog

    mail.outbox.clear()

    response = api_client.post(
        "/api/v1/auth/password-reset:request",
        {"email": user.email},
        format="json",
    )

    assert response.status_code == 204
    assert len(mail.outbox) == 1
    sent = cast(EmailMultiAlternatives, mail.outbox[0])
    assert sent.to == [user.email]
    html_body, _ = sent.alternatives[0]
    assert "reset-password?token=" in cast(str, html_body)

    log = EmailLog.objects.get(template_key="auth.password_reset")
    assert log.correlation == {"user_id": user.id, "purpose": "password_reset"}


@pytest.mark.django_db
def test_password_reset_request_is_silent_for_unknown_email(
    api_client: APIClient,
) -> None:
    from django.core import mail

    mail.outbox.clear()
    response = api_client.post(
        "/api/v1/auth/password-reset:request",
        {"email": "nobody@example.com"},
        format="json",
    )

    assert response.status_code == 204
    assert mail.outbox == []


@pytest.mark.usefixtures("run_on_commit_immediately")
@pytest.mark.django_db
def test_password_reset_request_is_idempotent_on_repeat(
    api_client: APIClient,
    user: User,
    system_smtp_profile: SmtpProfile,
) -> None:
    from django.core import mail

    from comms.models import EmailLog

    mail.outbox.clear()

    api_client.post(
        "/api/v1/auth/password-reset:request",
        {"email": user.email},
        format="json",
    )
    api_client.post(
        "/api/v1/auth/password-reset:request",
        {"email": user.email},
        format="json",
    )

    assert len(mail.outbox) == 1
    assert EmailLog.objects.filter(template_key="auth.password_reset").count() == 1


# --- password-reset:confirm --------------------------------------------------

_CONFIRM_URL = "/api/v1/auth/password-reset:confirm"
_NEW_PASSWORD = "brand new battery staple"


@pytest.mark.django_db
def test_password_reset_confirm_sets_new_password(
    api_client: APIClient, user: User, password: str
) -> None:
    from accounts.services.password_reset import _make_token

    token = _make_token(user)
    response = api_client.post(
        _CONFIRM_URL,
        {"token": token, "new_password": _NEW_PASSWORD},
        format="json",
    )

    assert response.status_code == 204
    user.refresh_from_db()
    assert user.check_password(_NEW_PASSWORD)
    assert not user.check_password(password)


@pytest.mark.django_db
@override_settings(PASSWORD_RESET_TTL_SECONDS=-1)
def test_password_reset_confirm_rejects_expired_token(api_client: APIClient, user: User) -> None:
    from accounts.services.password_reset import _make_token

    token = _make_token(user)
    response = api_client.post(
        _CONFIRM_URL,
        {"token": token, "new_password": _NEW_PASSWORD},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "password_reset_token_expired"


@pytest.mark.django_db
def test_password_reset_confirm_rejects_tampered_token(api_client: APIClient, user: User) -> None:
    response = api_client.post(
        _CONFIRM_URL,
        {"token": "not-a-real-token", "new_password": _NEW_PASSWORD},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "password_reset_token_invalid"


@pytest.mark.django_db
def test_password_reset_confirm_rejects_weak_password(api_client: APIClient, user: User) -> None:
    from accounts.services.password_reset import _make_token

    token = _make_token(user)
    response = api_client.post(
        _CONFIRM_URL,
        {"token": token, "new_password": "short"},
        format="json",
    )

    assert response.status_code == 400
    assert "new_password" in response.json()["field_errors"]


@pytest.mark.django_db
def test_password_reset_confirm_rejects_orphaned_token(api_client: APIClient, user: User) -> None:
    """A valid token whose user was since deactivated degrades to 400, not 500."""
    from accounts.services.password_reset import _make_token

    token = _make_token(user)
    user.is_active = False
    user.save(update_fields=["is_active"])

    response = api_client.post(
        _CONFIRM_URL,
        {"token": token, "new_password": _NEW_PASSWORD},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "password_reset_token_invalid"
