"""TOTP enrolment / challenge / verify / disable.

Backed by pyotp. SMS-based 2FA is reserved on the enum but not implemented.
Recovery codes are stored as pbkdf2 hashes via Django's make_password.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

import pyotp
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.signing import BadSignature, TimestampSigner
from django.db import transaction
from django.utils import timezone

from accounts.enums import TfaMethod
from accounts.models import User

_RECOVERY_CODE_COUNT = 10
_RECOVERY_CODE_LENGTH = 10
_CHALLENGE_TTL_SECONDS = 300

_signer = TimestampSigner(salt="accounts.two_factor")


def _new_recovery_codes() -> list[str]:
    return [
        "-".join([secrets.token_hex(2)] * 2)[:_RECOVERY_CODE_LENGTH]
        for _ in range(_RECOVERY_CODE_COUNT)
    ]


@dataclass(frozen=True)
class EnrollmentPayload:
    secret: str
    provisioning_uri: str
    recovery_codes: list[str]


@dataclass(frozen=True)
class ChallengeToken:
    token: str
    expires_in_seconds: int


class TfaError(Exception):
    pass


class TwoFactorService:
    """Stateless TOTP service. All side effects are explicit.

    Method preconditions are documented inline; failure modes raise the
    typed TfaError. Views translate that to a 4xx response.
    """

    @staticmethod
    def enroll(user: User) -> EnrollmentPayload:
        """Generate a fresh secret + recovery codes.

        Persists encrypted secret + hashed recovery codes; leaves tfa_method
        at NONE until confirm_enrollment succeeds against the new secret.
        """
        secret = pyotp.random_base32()
        recovery = _new_recovery_codes()
        hashed = [make_password(code) for code in recovery]
        with transaction.atomic():
            user.tfa_secret = secret
            user.tfa_recovery_codes = hashed
            user.save(update_fields=["tfa_secret", "tfa_recovery_codes"])
        issuer = getattr(settings, "TFA_ISSUER", "Villa Collective")
        provisioning = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=issuer)
        return EnrollmentPayload(
            secret=secret,
            provisioning_uri=provisioning,
            recovery_codes=recovery,
        )

    @staticmethod
    def confirm_enrollment(user: User, code: str) -> bool:
        """Verify the first TOTP code, flip tfa_method=TOTP on success."""
        if not user.tfa_secret:
            raise TfaError("No pending enrollment")
        if not pyotp.TOTP(user.tfa_secret).verify(code, valid_window=1):
            return False
        user.tfa_method = TfaMethod.TOTP
        user.tfa_enrolled_at = timezone.now()
        user.save(update_fields=["tfa_method", "tfa_enrolled_at"])
        return True

    @staticmethod
    def challenge(user: User) -> ChallengeToken:
        if user.tfa_method != TfaMethod.TOTP:
            raise TfaError("2FA not enrolled")
        token = _signer.sign(str(user.pk))
        return ChallengeToken(token=token, expires_in_seconds=_CHALLENGE_TTL_SECONDS)

    @staticmethod
    def verify(challenge_token: str, code: str) -> User:
        try:
            value = _signer.unsign(challenge_token, max_age=_CHALLENGE_TTL_SECONDS)
        except BadSignature as exc:
            raise TfaError("Invalid or expired challenge token") from exc
        user = User.objects.get(pk=int(value))
        if user.tfa_method != TfaMethod.TOTP or not user.tfa_secret:
            raise TfaError("2FA not enrolled for this user")
        if pyotp.TOTP(user.tfa_secret).verify(code, valid_window=1):
            return user
        # Recovery code fallback (single-use): check + consume on match.
        for idx, hashed in enumerate(user.tfa_recovery_codes):
            if check_password(code, hashed):
                user.tfa_recovery_codes = (
                    user.tfa_recovery_codes[:idx] + user.tfa_recovery_codes[idx + 1 :]
                )
                user.save(update_fields=["tfa_recovery_codes"])
                return user
        # Light rate-limit hook — view layer wraps with django-axes or similar.
        time.sleep(0.05)
        raise TfaError("Invalid TOTP code")

    @staticmethod
    @transaction.atomic
    def disable(user: User) -> None:
        user.tfa_method = TfaMethod.NONE
        user.tfa_secret = ""
        user.tfa_enrolled_at = None
        user.tfa_recovery_codes = []
        user.save(
            update_fields=[
                "tfa_method",
                "tfa_secret",
                "tfa_enrolled_at",
                "tfa_recovery_codes",
            ]
        )
