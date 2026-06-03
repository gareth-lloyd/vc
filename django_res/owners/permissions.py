"""DRF permission for owner-portal endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.permissions import BasePermission

from owners.enums import OwnerMembershipStatus, OwnerOrgStatus

if TYPE_CHECKING:
    from django.contrib.auth.models import AnonymousUser
    from rest_framework.request import Request
    from rest_framework.views import APIView

    from accounts.models import User


def is_owner(user: User | AnonymousUser) -> bool:
    """True iff `user` holds an ACTIVE membership of an ACTIVE owner org.

    The org-status check mirrors `owners.scoping._active_grants`: suspending
    an org must actually lock its members out of the portal, not admit them
    to an empty shell. Without it the gate and the data layer would disagree.
    """
    from owners.models import OwnerMembership

    if not user.is_authenticated:
        return False
    return OwnerMembership.objects.filter(
        user=user,
        status=OwnerMembershipStatus.ACTIVE,
        organisation__status=OwnerOrgStatus.ACTIVE,
    ).exists()


class IsOwner(BasePermission):
    """Grant access only to users with an ACTIVE membership of an ACTIVE org.

    Staff-only users (no membership) are rejected with 403; the SPA chooses
    its shell from which of `/auth/me` / `/owner/me` succeeds.
    """

    message = "Owner access required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return is_owner(request.user)
