"""Request middleware enforcing TOTP enrolment for staff (GAP-057).

When ``settings.TFA_ENFORCED`` is on, an authenticated ``is_staff`` user whose
``tfa_method`` is still ``NONE`` may reach only the enrolment allowlist; every
other ``/api/`` path returns 403 ``tfa_enrollment_required`` (canonical error
envelope). The ``/api/`` scope is load-bearing: without it the middleware would
403 the SPA HTML shell and static assets, and the user could never *render* the
enrolment page. Django admin (``/admin/``) is therefore unenforced — acceptable
per the ticket scope ("to use the API") and necessary for boot.
"""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from accounts.enums import TfaMethod

# Full ``/api/v1/…`` paths (accounts is mounted at ``/api/v1/``). The minimum a
# logged-in-but-unenrolled staff user needs to complete enrolment and nothing
# else. ``auth/2fa:verify`` is AllowAny (pre-session) and unaffected.
_ALLOWLIST = frozenset(
    {
        "/api/v1/auth/csrf",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/auth/permissions",
        "/api/v1/auth/2fa:enroll",
    }
)

_DETAIL = "Two-factor authentication must be set up before you can use the API."


def tfa_enrollment_required_payload() -> dict[str, object]:
    """The canonical error envelope body for a blocked-on-enrolment response."""
    return {"code": "tfa_enrollment_required", "detail": _DETAIL, "field_errors": {}}


def tfa_enrollment_required_response() -> JsonResponse:
    """The 403 the enforcement middleware emits (plain Django, no DRF request)."""
    return JsonResponse(tfa_enrollment_required_payload(), status=403)


class TfaEnforcementMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if self._should_block(request):
            return tfa_enrollment_required_response()
        return self.get_response(request)

    @staticmethod
    def _should_block(request: HttpRequest) -> bool:
        # Read the flag per-request so override_settings(TFA_ENFORCED=True)
        # takes effect in tests (never cache it in __init__).
        if not settings.TFA_ENFORCED:
            return False
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or not user.is_staff:
            return False
        if user.tfa_method != TfaMethod.NONE:
            return False
        path = request.path
        if not path.startswith("/api/"):
            return False
        return path not in _ALLOWLIST
