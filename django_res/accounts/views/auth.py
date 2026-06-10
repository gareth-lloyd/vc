"""Authentication, session, profile, and 2FA endpoints.

Views are thin shells: they validate input via serializers and delegate every
side effect to a service (`TwoFactorService`, `SessionService`, the
`django.contrib.auth` functions). Business logic does not live here.
"""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.enums import TfaMethod
from accounts.models import User, UserSession
from accounts.serializers import (
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetRequestSerializer,
    SessionInfoSerializer,
    TfaChallengeSerializer,
    TfaEnrollSerializer,
    TfaVerifySerializer,
    UserMeSerializer,
)
from accounts.services import SessionService, TwoFactorService
from accounts.services.password_reset import PasswordResetService
from accounts.services.two_factor import TfaError
from core.api import not_implemented_response


class CsrfView(APIView):
    """`GET /auth/csrf` — prime the `csrftoken` cookie for the SPA.

    The SPA calls this on boot, so the first session-authenticated POST
    (typically `/auth/login`) already carries the cookie regardless of which
    server delivered the HTML shell — Vite dev server on :5173, single-origin
    Django, or staging. Without it, a fresh browser's first login submit is
    403'd by `CsrfViewMiddleware` and the user has to submit twice.
    """

    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request: Request) -> Response:
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoginView(APIView):
    """`POST /auth/login` — credential login, sets the session cookie.

    If the user has 2FA enrolled, returns a `challenge_token` instead of
    completing the session. The caller then submits the OTP to
    `POST /auth/2fa:verify` to finalise login.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth.login"

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        user = authenticate(request, username=email, password=password)
        if user is None or not user.is_active:
            return Response(
                {
                    "code": "invalid_credentials",
                    "detail": "Invalid email or password.",
                    "field_errors": {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if user.tfa_method == TfaMethod.TOTP:
            challenge = TwoFactorService.challenge(user)
            return Response(
                {
                    "tfa_required": True,
                    "challenge_token": challenge.token,
                    "expires_in_seconds": challenge.expires_in_seconds,
                }
            )
        login(request, user)
        return Response({"tfa_required": False, "user": UserMeSerializer(user).data})


class LogoutView(APIView):
    """`POST /auth/logout` — invalidates the session cookie."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """`GET/PATCH /auth/me`."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(UserMeSerializer(cast(User, request.user)).data)

    def patch(self, request: Request) -> Response:
        serializer = UserMeSerializer(cast(User, request.user), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PasswordChangeView(APIView):
    """`POST /auth/me/password` — change own password."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = cast(User, request.user)
        if not user.check_password(serializer.validated_data["current_password"]):
            return Response(
                {
                    "code": "invalid_credentials",
                    "detail": "Current password is incorrect.",
                    "field_errors": {"current_password": ["Incorrect"]},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PermissionsView(APIView):
    """`GET /auth/permissions` — caller's role + `auth.Permission` codenames."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user
        return Response(
            {
                "role": getattr(user, "role", None),
                "is_superuser": bool(getattr(user, "is_superuser", False)),
                "permissions": sorted(cast(User, user).get_all_permissions()),
            }
        )


class AuthSessionViewSet(viewsets.ViewSet):
    """`GET /auth/sessions`, `DELETE /auth/sessions/{id}`.

    `id` is the `UserSession.id` (numeric PK), not the session_key, so we
    don't leak raw session keys into URLs.
    """

    permission_classes = [IsAuthenticated]

    def list(self, request: Request) -> Response:
        info = SessionService.list_for_user(cast(User, request.user))
        payload = [
            {
                "session_key": s.session_key,
                "created_at": s.created_at,
                "last_seen_at": s.last_seen_at,
                "user_agent": s.user_agent,
                "ip": s.ip,
            }
            for s in info
        ]
        return Response(SessionInfoSerializer(cast(Any, payload), many=True).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        row = get_object_or_404(
            UserSession,
            pk=pk,
            user=cast(User, request.user),
            revoked_at__isnull=True,
        )
        SessionService.revoke(row.session_key)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TfaEnrollView(APIView):
    """`POST /auth/2fa:enroll` — start TOTP enrolment (or confirm w/ code)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = TfaEnrollSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data.get("code") or ""
        user = cast(User, request.user)
        if code:
            ok = TwoFactorService.confirm_enrollment(user, code)
            if not ok:
                return Response(
                    {
                        "code": "invalid_tfa_code",
                        "detail": "Invalid TOTP code.",
                        "field_errors": {},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response({"enrolled": True, "tfa_method": user.tfa_method})

        payload = TwoFactorService.enroll(user)
        return Response(
            {
                "secret": payload.secret,
                "provisioning_uri": payload.provisioning_uri,
                "recovery_codes": payload.recovery_codes,
            }
        )


class TfaChallengeView(APIView):
    """`POST /auth/2fa:challenge` — credentials → challenge_token.

    Equivalent to /auth/login when TFA is enabled — kept as a separate
    endpoint so flows that already know the user is enrolled can be explicit.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth.tfa"

    def post(self, request: Request) -> Response:
        serializer = TfaChallengeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        user = authenticate(request, username=email, password=password)
        if user is None or not user.is_active:
            return Response(
                {
                    "code": "invalid_credentials",
                    "detail": "Invalid credentials.",
                    "field_errors": {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            challenge = TwoFactorService.challenge(user)
        except TfaError as exc:
            return Response(
                {"code": "tfa_not_enrolled", "detail": str(exc), "field_errors": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "challenge_token": challenge.token,
                "expires_in_seconds": challenge.expires_in_seconds,
            }
        )


class TfaVerifyView(APIView):
    """`POST /auth/2fa:verify` — submit OTP → completes login."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth.tfa"

    def post(self, request: Request) -> Response:
        serializer = TfaVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = TwoFactorService.verify(
                serializer.validated_data["challenge_token"],
                serializer.validated_data["code"],
            )
        except TfaError as exc:
            return Response(
                {"code": "invalid_tfa_code", "detail": str(exc), "field_errors": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, user)
        return Response({"user": UserMeSerializer(user).data})


class TfaDisableView(APIView):
    """`POST /auth/2fa:disable` — clear own enrolment."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        TwoFactorService.disable(cast(User, request.user))
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- 501 placeholders for endpoints whose comms wiring isn't ready yet -----


class PasswordResetRequestView(APIView):
    """`POST /auth/password-reset:request` — start the email-based reset flow.

    Always returns 204 regardless of whether the email matches a real user
    so the endpoint can't be used to enumerate registered addresses.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth.password_reset"

    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PasswordResetService.request(serializer.validated_data["email"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth.password_reset"

    def post(self, request: Request) -> Response:
        return not_implemented_response("Password reset confirmation is not yet wired.")


class MagicLinkRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        return not_implemented_response("Magic-link auth is not yet wired in MVP.")


class MagicLinkConsumeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        return not_implemented_response("Magic-link auth is not yet wired in MVP.")
