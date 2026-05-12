"""Staff user CRUD + admin actions (`/users`)."""

from __future__ import annotations

from typing import Any, cast

from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import User, UserSession
from accounts.serializers import (
    SessionInfoSerializer,
    UserCreateSerializer,
    UserSerializer,
)
from accounts.services import SessionService, TwoFactorService
from core.api import IsStaffRoleAdmin, not_implemented_response


class UserFilterSet(FilterSet):
    class Meta:
        model = User
        fields = {
            "role": ["exact"],
            "is_active": ["exact"],
        }


class UserViewSet(viewsets.ModelViewSet[User]):
    """`/users` — CRUD + admin actions.

    Reads available to any authenticated user (staff list visibility);
    writes and destructive actions require `IsStaffRoleAdmin`.
    """

    queryset = User.objects.all().order_by("email")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = UserFilterSet
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["email", "date_joined", "last_login"]

    def get_serializer_class(self) -> type:
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer

    def get_permissions(self) -> list[Any]:
        if self.action in {"list", "retrieve"}:
            return [IsAuthenticated()]
        return [IsStaffRoleAdmin()]

    def perform_destroy(self, instance: User) -> None:
        # Per spec: DELETE deactivates rather than hard-deleting (audit + FK
        # integrity matters; auth.User has many incoming FKs).
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request: Request, pk: str | None = None) -> Response:
        """Re-enable a deactivated staff user."""
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request: Request, pk: str | None = None) -> Response:
        """Admin-initiated password reset.

        Email dispatch isn't wired in MVP, so this returns 501. When comms
        lands, swap for a service call that mints + emails a single-use token.
        """
        return not_implemented_response(
            "Admin password reset is not yet wired. "
            "Use Django's setpassword management command for now."
        )

    @action(detail=True, methods=["post"], url_path="reset-2fa")
    def reset_tfa(self, request: Request, pk: str | None = None) -> Response:
        """Clear the user's 2FA enrolment (admin-only)."""
        user = self.get_object()
        TwoFactorService.disable(user)
        return Response({"reset": True, "user_id": user.pk})


class UserSessionsView(viewsets.ViewSet):
    """`GET /users/{user_id}/sessions`."""

    permission_classes = [IsStaffRoleAdmin]

    def list(self, request: Request, user_pk: str | None = None) -> Response:
        target = get_object_or_404(User, pk=user_pk)
        info = SessionService.list_for_user(target)
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


class UserSessionRevokeView(viewsets.ViewSet):
    """`DELETE /users/{user_id}/sessions/{session_id}` — admin session revoke."""

    permission_classes = [IsStaffRoleAdmin]

    def destroy(
        self,
        request: Request,
        user_pk: str | None = None,
        pk: str | None = None,
    ) -> Response:
        row = get_object_or_404(
            UserSession,
            pk=pk,
            user_id=user_pk,
            revoked_at__isnull=True,
        )
        SessionService.revoke(row.session_key)
        return Response(status=status.HTTP_204_NO_CONTENT)
