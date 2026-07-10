"""The `users` stage pre-enrols the primary dev superuser in TOTP 2FA.

2FA state lives as encrypted columns on ``accounts_user`` (there is no separate
device table), so a dropped-and-reseeded DB would otherwise strip any enrolled
authenticator secret. The stage seeds a *fixed* secret onto ``glloyd@gmail.com``
so the same authenticator codes keep working across reseeds. See
``seeding/stages/users.py``.
"""

from __future__ import annotations

import random

import pyotp
import pytest

from accounts.enums import TfaMethod
from accounts.models import User
from accounts.services.two_factor import TwoFactorService
from seeding.context import _PROFILES, Profile, SeedContext
from seeding.stages.users import _DEV_TFA_SECRET, _run

pytestmark = pytest.mark.django_db


def _ctx() -> SeedContext:
    """A minimal context that seeds only the fixed superusers (no random users)."""
    return SeedContext(
        rng=random.Random(0),
        knobs=_PROFILES[Profile.HAPPY],
        n_properties=0,
        n_bookings=0,
        n_users=0,
    )


def test_glloyd_superuser_is_pre_enrolled_with_the_stable_totp_secret() -> None:
    _run(_ctx())

    user = User.objects.get(email="glloyd@gmail.com")
    assert user.tfa_method == TfaMethod.TOTP
    # Decrypts on read; the seeded plaintext base32 round-trips.
    assert user.tfa_secret == _DEV_TFA_SECRET
    assert user.tfa_enrolled_at is not None
    # The seeded secret is a working, decryptable enrolment: a live code verifies
    # (compute once, verify once — verify_code consumes the timestep).
    code = pyotp.TOTP(user.tfa_secret).now()
    assert TwoFactorService.verify_code(user, code) is True


@pytest.mark.django_db
def test_enforced_environments_never_get_the_public_secret() -> None:
    """On staging/production (TFA_ENFORCED) 2FA is a real control — never inject
    the repo-committed secret there, or its second factor would be public."""
    from django.test import override_settings

    with override_settings(TFA_ENFORCED=True):
        _run(_ctx())

    user = User.objects.get(email="glloyd@gmail.com")
    assert user.tfa_method == TfaMethod.NONE
    assert user.tfa_secret == ""


def test_nick_superuser_stays_password_only() -> None:
    _run(_ctx())

    nick = User.objects.get(email="nick@villacollective.com")
    assert nick.tfa_method == TfaMethod.NONE
    assert nick.tfa_secret == ""


def test_ben_superuser_stays_password_only() -> None:
    _run(_ctx())

    ben = User.objects.get(email="ben@mojomedia.co.uk")
    assert ben.is_superuser is True
    assert ben.tfa_method == TfaMethod.NONE
    assert ben.tfa_secret == ""


def test_reseeding_is_idempotent_and_preserves_enrolment() -> None:
    _run(_ctx())
    _run(_ctx())  # additive re-seed against a live DB must not duplicate or reset

    users = User.objects.filter(email="glloyd@gmail.com")
    assert users.count() == 1
    assert users.get().tfa_method == TfaMethod.TOTP
