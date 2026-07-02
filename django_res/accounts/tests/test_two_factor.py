from __future__ import annotations

import pyotp
import pytest

from accounts.enums import TfaMethod
from accounts.models import User
from accounts.services import TwoFactorService
from accounts.services import two_factor as two_factor_module
from accounts.services.two_factor import TfaError

# A fixed epoch mid-timestep so cur-1/cur/cur+1 codes are unambiguous.
_FROZEN_NOW = 1_700_000_015
_STEP = 30


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user(email="agent@example.com", password="pw")


@pytest.fixture
def frozen_now(monkeypatch: pytest.MonkeyPatch) -> int:
    """Pin the service clock so TOTP timesteps are deterministic."""
    monkeypatch.setattr(two_factor_module.time, "time", lambda: float(_FROZEN_NOW))
    return _FROZEN_NOW


@pytest.fixture
def enrolled_user(user: User) -> User:
    payload = TwoFactorService.enroll(user)
    TwoFactorService.confirm_enrollment(user, pyotp.TOTP(payload.secret).now())
    user.refresh_from_db()
    return user


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


# --- verify_code: single-use replay guard (Unit 1) ---


@pytest.mark.django_db
def test_verify_code_accepts_fresh_code_once(enrolled_user: User, frozen_now: int) -> None:
    secret = enrolled_user.tfa_secret
    code = pyotp.TOTP(secret).at(frozen_now)

    assert TwoFactorService.verify_code(enrolled_user, code) is True
    enrolled_user.refresh_from_db()
    assert enrolled_user.tfa_last_verified_step == frozen_now // _STEP

    # Replaying the very same code in the same window is refused.
    assert TwoFactorService.verify_code(enrolled_user, code) is False


@pytest.mark.django_db
def test_verify_code_rejects_stale_earlier_step(enrolled_user: User, frozen_now: int) -> None:
    # Consume the current step first.
    current = pyotp.TOTP(enrolled_user.tfa_secret).at(frozen_now)
    assert TwoFactorService.verify_code(enrolled_user, current) is True

    # A still-in-window code from the previous step is now stale (its step
    # is <= the last consumed step) and must be refused.
    previous = pyotp.TOTP(enrolled_user.tfa_secret).at(frozen_now - _STEP)
    assert TwoFactorService.verify_code(enrolled_user, previous) is False


@pytest.mark.django_db
def test_verify_code_accepts_window_edge_codes(enrolled_user: User, frozen_now: int) -> None:
    # A code from the previous step (cur-1) is within the ±1 window.
    previous = pyotp.TOTP(enrolled_user.tfa_secret).at(frozen_now - _STEP)
    assert TwoFactorService.verify_code(enrolled_user, previous) is True
    enrolled_user.refresh_from_db()
    assert enrolled_user.tfa_last_verified_step == (frozen_now - _STEP) // _STEP

    # A code from the next step (cur+1) is still ahead of the consumed step.
    nxt = pyotp.TOTP(enrolled_user.tfa_secret).at(frozen_now + _STEP)
    assert TwoFactorService.verify_code(enrolled_user, nxt) is True
    enrolled_user.refresh_from_db()
    assert enrolled_user.tfa_last_verified_step == (frozen_now + _STEP) // _STEP


@pytest.mark.django_db
def test_verify_code_rejects_recovery_code(user: User, frozen_now: int) -> None:
    # Recovery codes are a login-only escape hatch; verify_code (the raw
    # step-up path) must not accept them.
    payload = TwoFactorService.enroll(user)
    TwoFactorService.confirm_enrollment(user, pyotp.TOTP(payload.secret).now())
    user.refresh_from_db()

    assert TwoFactorService.verify_code(user, payload.recovery_codes[0]) is False


@pytest.mark.django_db
def test_verify_code_rejects_unenrolled_user(user: User, frozen_now: int) -> None:
    # No TOTP secret / method NONE ⇒ nothing to verify against.
    assert TwoFactorService.verify_code(user, "000000") is False


@pytest.mark.django_db
def test_login_verify_shares_replay_guard(enrolled_user: User, frozen_now: int) -> None:
    # The login challenge path now funnels its TOTP branch through verify_code,
    # so a login-consumed code cannot be replayed on a second challenge.
    code = pyotp.TOTP(enrolled_user.tfa_secret).at(frozen_now)
    challenge = TwoFactorService.challenge(enrolled_user)
    assert TwoFactorService.verify(challenge.token, code).pk == enrolled_user.pk

    challenge2 = TwoFactorService.challenge(enrolled_user)
    with pytest.raises(TfaError):
        TwoFactorService.verify(challenge2.token, code)
