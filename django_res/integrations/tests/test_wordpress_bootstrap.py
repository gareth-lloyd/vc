"""WP inbound auth plumbing: settings + the `bootstrap_wordpress_user` command.

The design (08-integrations.md §"Inbound: WordPress → Django") mandates DRF
TokenAuthentication with a dedicated non-staff service user whose token is the
only credential. The spec pins the user by *username*; our User model is
email-keyed (`username = None`), so the pin is `settings.WORDPRESS_SERVICE_EMAIL`.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.conf import settings
from django.core.management import call_command
from rest_framework.authtoken.models import Token

from accounts.models import User

pytestmark = pytest.mark.django_db


def _bootstrap(*args: str) -> str:
    out = StringIO()
    call_command("bootstrap_wordpress_user", *args, stdout=out)
    return out.getvalue()


def _service_user() -> User:
    return User.objects.get(email=settings.WORDPRESS_SERVICE_EMAIL)


def test_authtoken_app_installed() -> None:
    assert "rest_framework.authtoken" in settings.INSTALLED_APPS


def test_wordpress_inbound_throttle_scope_in_base_and_test_settings() -> None:
    # settings/test.py replaces DEFAULT_THROTTLE_RATES wholesale, so the scope
    # must exist in BOTH dicts or ScopedRateThrottle raises ImproperlyConfigured
    # on every endpoint test while base (staging/production) silently drifts.
    from villacollective.settings import base

    for conf in (base.REST_FRAMEWORK, settings.REST_FRAMEWORK):
        rates = conf["DEFAULT_THROTTLE_RATES"]
        assert isinstance(rates, dict)
        assert "wordpress_inbound" in rates


def test_token_authentication_stays_out_of_the_drf_defaults() -> None:
    # Containment: the WP token must only work on views that opt in with
    # `authentication_classes = [TokenAuthentication]`. Enabling it globally
    # would give a leaked token session-equivalent reach over the whole API.
    from villacollective.settings import base

    for conf in (base.REST_FRAMEWORK, settings.REST_FRAMEWORK):
        auth_classes = conf.get("DEFAULT_AUTHENTICATION_CLASSES", [])
        assert isinstance(auth_classes, list)
        assert not any("TokenAuthentication" in cls for cls in auth_classes)


def test_bootstrap_creates_locked_down_service_user_with_token() -> None:
    output = _bootstrap()

    user = _service_user()
    assert user.is_active
    assert not user.is_staff
    assert not user.is_superuser
    assert not user.has_usable_password()

    token = Token.objects.get(user=user)
    assert token.key in output


def test_bootstrap_is_idempotent() -> None:
    _bootstrap()
    key_before = Token.objects.get(user=_service_user()).key

    _bootstrap()

    assert User.objects.filter(email=settings.WORDPRESS_SERVICE_EMAIL).count() == 1
    assert Token.objects.get(user=_service_user()).key == key_before


def test_bootstrap_rotate_replaces_the_token() -> None:
    _bootstrap()
    key_before = Token.objects.get(user=_service_user()).key

    _bootstrap("--rotate")

    tokens = Token.objects.filter(user=_service_user())
    assert tokens.count() == 1
    assert tokens.get().key != key_before


def test_bootstrap_converges_a_tampered_user_back_to_locked_down() -> None:
    user = User.objects.create(
        email=settings.WORDPRESS_SERVICE_EMAIL,
        is_staff=True,
        is_superuser=True,
    )
    user.set_password("hunter2")
    user.save()

    _bootstrap()

    user.refresh_from_db()
    assert not user.is_staff
    assert not user.is_superuser
    assert not user.has_usable_password()
