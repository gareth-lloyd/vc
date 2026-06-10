"""Anti-brute-force throttles on the unauthenticated auth endpoints.

Scoped DRF throttles (anon, keyed by IP) on login, 2FA challenge/verify
and password reset. Test settings relax the configured rates so the rest
of the suite's logins never trip them; these tests pin behaviour by
patching `SimpleRateThrottle.THROTTLE_RATES` directly — DRF snapshots
that dict as a class attribute at import time, so `override_settings`
on `REST_FRAMEWORK` is order-dependent and unreliable here.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.core.cache import cache
from rest_framework.throttling import SimpleRateThrottle

pytestmark = pytest.mark.django_db

_TIGHT_RATES = {
    "auth.login": "3/min",
    "auth.tfa": "3/min",
    "auth.password_reset": "3/min",
}


@pytest.fixture(autouse=True)
def _tight_throttle_rates(monkeypatch: pytest.MonkeyPatch) -> None:
    cache.clear()
    monkeypatch.setattr(SimpleRateThrottle, "THROTTLE_RATES", _TIGHT_RATES)


def test_login_throttles_after_rate_exceeded(client: Any) -> None:
    for _ in range(3):
        response = client.post(
            "/api/v1/auth/login",
            {"email": "nobody@example.com", "password": "wrong"},
            content_type="application/json",
        )
        assert response.status_code != 429

    response = client.post(
        "/api/v1/auth/login",
        {"email": "nobody@example.com", "password": "wrong"},
        content_type="application/json",
    )
    assert response.status_code == 429


def test_password_reset_request_throttles(client: Any) -> None:
    for _ in range(3):
        client.post(
            "/api/v1/auth/password-reset:request",
            {"email": "nobody@example.com"},
            content_type="application/json",
        )

    response = client.post(
        "/api/v1/auth/password-reset:request",
        {"email": "nobody@example.com"},
        content_type="application/json",
    )
    assert response.status_code == 429


def test_tfa_verify_throttles(client: Any) -> None:
    for _ in range(3):
        client.post(
            "/api/v1/auth/2fa:verify",
            {"token": "nope", "code": "000000"},
            content_type="application/json",
        )

    response = client.post(
        "/api/v1/auth/2fa:verify",
        {"token": "nope", "code": "000000"},
        content_type="application/json",
    )
    assert response.status_code == 429
