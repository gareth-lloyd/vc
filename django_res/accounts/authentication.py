"""DRF authentication classes tied to the staff 2FA policy (GAP-057).

``BasicAuthentication`` is enabled globally so the owner iCal calendar feed
(non-staff, machine-consumed) can authenticate. But Basic auth is a
password-only path that runs at the DRF view layer — *after*
``TfaEnforcementMiddleware`` has already seen ``request.user`` as anonymous
(the middleware only reads the session). Left unrestricted it would let a staff
principal skip both the 2FA login challenge and the enrolment enforcement.

``StaffExcludedBasicAuthentication`` closes that hole: staff must sign in
through the session flow (where the login 2FA challenge and the enforcement
middleware apply); Basic auth stays available to non-staff owner principals.
"""

from __future__ import annotations

from typing import Any

from rest_framework.authentication import BasicAuthentication
from rest_framework.exceptions import AuthenticationFailed


class StaffExcludedBasicAuthentication(BasicAuthentication):
    def authenticate_credentials(
        self, userid: str, password: str, request: Any = None
    ) -> tuple[Any, Any]:
        user, auth = super().authenticate_credentials(userid, password, request)
        if user.is_staff:
            # Force staff onto the session flow so 2FA (login challenge +
            # enrolment enforcement) cannot be side-stepped via Basic auth.
            raise AuthenticationFailed(
                "Staff accounts must authenticate through the session login "
                "flow; HTTP Basic auth is not permitted for staff."
            )
        return user, auth
