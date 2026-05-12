from __future__ import annotations

import pyotp
import pytest

from accounts.enums import TfaMethod
from accounts.models import User
from accounts.services import TwoFactorService
from accounts.services.two_factor import TfaError


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user(email="agent@example.com", password="pw")


@pytest.mark.django_db
def test_enroll_confirm_flow(user: User) -> None:
    payload = TwoFactorService.enroll(user)
    code = pyotp.TOTP(payload.secret).now()

    assert TwoFactorService.confirm_enrollment(user, code)
    user.refresh_from_db()
    assert user.tfa_method == TfaMethod.TOTP
    assert user.tfa_enrolled_at is not None


@pytest.mark.django_db
def test_verify_with_totp_then_disable(user: User) -> None:
    payload = TwoFactorService.enroll(user)
    TwoFactorService.confirm_enrollment(user, pyotp.TOTP(payload.secret).now())

    challenge = TwoFactorService.challenge(user)
    verified = TwoFactorService.verify(challenge.token, pyotp.TOTP(payload.secret).now())

    assert verified.pk == user.pk

    TwoFactorService.disable(user)
    user.refresh_from_db()
    assert user.tfa_method == TfaMethod.NONE
    assert user.tfa_secret == ""


@pytest.mark.django_db
def test_recovery_code_consumes_single_use(user: User) -> None:
    payload = TwoFactorService.enroll(user)
    TwoFactorService.confirm_enrollment(user, pyotp.TOTP(payload.secret).now())
    challenge = TwoFactorService.challenge(user)

    recovery = payload.recovery_codes[0]
    user_after = TwoFactorService.verify(challenge.token, recovery)
    assert user_after.pk == user.pk

    challenge2 = TwoFactorService.challenge(user)
    with pytest.raises(TfaError):
        TwoFactorService.verify(challenge2.token, recovery)
