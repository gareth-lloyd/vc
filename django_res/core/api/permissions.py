"""Custom DRF permission classes for the Villa Collective API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.enums import StaffRole

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView


def _user_role(request: Request) -> str | None:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    if getattr(user, "is_superuser", False):
        return StaffRole.ADMIN.value
    role = getattr(user, "role", None)
    return role if isinstance(role, str) else None


class IsStaffRoleAdmin(BasePermission):
    """Grant access to superusers and users whose `User.role` is `ADMIN`.

    Used to gate destructive / privileged operations (user CRUD, audit-log read,
    contact deletion, etc.) that should not be exposed to reservation or viewer
    roles.
    """

    message = "Admin role required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return _user_role(request) == StaffRole.ADMIN.value


class IsReservationsWriter(BasePermission):
    """Read for any authenticated user; write for ADMIN or RESERVATIONS roles."""

    message = "Reservations role required for write access."

    def has_permission(self, request: Request, view: APIView) -> bool:
        role = _user_role(request)
        if role is None:
            return False
        if request.method in SAFE_METHODS:
            return True
        return role in (StaffRole.ADMIN.value, StaffRole.RESERVATIONS.value)


class AllowAnyReadStaffWrite(BasePermission):
    """Anonymous reads allowed; writes restricted to ADMIN or RESERVATIONS roles.

    Used by metadata endpoints (countries, regions, features, categories…)
    that are public-readable but admin-writable.
    """

    message = "Reservations role required for write access."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if request.method in SAFE_METHODS:
            return True
        role = _user_role(request)
        if role is None:
            return False
        return role in (StaffRole.ADMIN.value, StaffRole.RESERVATIONS.value)


class IsAccountsWriter(BasePermission):
    """Read for any authenticated user; write for ADMIN or ACCOUNTS roles.

    Used to gate payment / refund / track action endpoints.
    """

    message = "Accounts role required for write access."

    def has_permission(self, request: Request, view: APIView) -> bool:
        role = _user_role(request)
        if role is None:
            return False
        if request.method in SAFE_METHODS:
            return True
        return role in (StaffRole.ADMIN.value, StaffRole.ACCOUNTS.value)
