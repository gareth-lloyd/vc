"""Password-reset request and confirmation.

The request flow generates a signed, time-limited token, builds a URL into
the SPA, and dispatches it via ``comms.EmailService``. The endpoint is
silent on whether the email is registered (no enumeration leak).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

from accounts.models import User
from comms.services import EmailService
from core.exceptions import DomainError

_TEMPLATE_KEY = "auth.password_reset"
_signer = TimestampSigner(salt="accounts.password_reset")


@dataclass(frozen=True)
class PasswordResetToken:
    user_id: int
    raw: str


def _make_token(user: User) -> str:
    return _signer.sign(str(user.pk))


def _verify_token(raw: str) -> int:
    try:
        unsigned = _signer.unsign(raw, max_age=settings.PASSWORD_RESET_TTL_SECONDS)
    except SignatureExpired as exc:
        raise PasswordResetTokenExpired() from exc
    except BadSignature as exc:
        raise PasswordResetTokenInvalid() from exc
    return int(unsigned)


def _build_reset_url(token: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/reset-password?{urlencode({'token': token})}"


class PasswordResetTokenExpired(DomainError):
    code = "password_reset_token_expired"
    status_code = 401


class PasswordResetTokenInvalid(DomainError):
    code = "password_reset_token_invalid"
    status_code = 400


class PasswordResetService:
    """Stateless. Email-based password recovery."""

    @staticmethod
    def request(email: str) -> None:
        """Send a reset email to ``email`` if it matches a real user.

        Silent when no user matches (no information leak). Idempotent on
        repeat — comms.EmailService dedupes on
        ``(template_key, version, sorted(to), correlation)``.
        """
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is None:
            return
        token = _make_token(user)
        EmailService.send(
            template_key=_TEMPLATE_KEY,
            context={
                "user_first_name": user.first_name or "",
                "reset_url": _build_reset_url(token),
                "expires_in_minutes": settings.PASSWORD_RESET_TTL_SECONDS // 60,
            },
            to=[user.email],
            correlation={"user_id": user.pk, "purpose": "password_reset"},
        )

    @staticmethod
    def consume(token: str, new_password: str) -> User:
        """Verify the token and apply the new password.

        Raises ``PasswordResetTokenExpired`` or ``PasswordResetTokenInvalid``
        on failure; both are 4xx-level errors, not 5xx.
        """
        user_id = _verify_token(token)
        user = User.objects.get(pk=user_id, is_active=True)
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return user
