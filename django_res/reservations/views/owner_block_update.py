"""Staff-facing owner-block awareness feed (`/owner-block-updates`).

Staff are aware observers, not gatekeepers: this is a chronological feed of
owner-block change events, each markable *seen* per staff user, and each
contestable (which flags the block and emails the owner but keeps it approved).

`get_queryset` annotates `is_seen` for the calling user and select_related's the
FKs the serializer walks, so the list serves one row and a hundred in the same
query count (pinned by `assert_max_queries`). Reads + `:seen`/`:unseen` are open
to any staff user; `:contest` is gated to reservations writers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.api.permissions import IsReservationsWriter, IsStaff
from reservations.models import OwnerBlockUpdate, OwnerBlockUpdateSeen
from reservations.serializers.owner_block_update import (
    OwnerBlockContestSerializer,
    OwnerBlockUpdateSerializer,
)
from reservations.services.owner_block import OwnerBlockService

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.permissions import BasePermission
    from rest_framework.request import Request

    from accounts.models import User


class OwnerBlockUpdateViewSet(viewsets.GenericViewSet):
    """`/owner-block-updates` — chronological feed + per-user seen + contest."""

    serializer_class = OwnerBlockUpdateSerializer

    def get_permissions(self) -> list[BasePermission]:
        # Contesting a block writes (notifies the owner), so it needs the
        # reservations-writer floor; everything else is read-or-seen for any
        # staff user.
        if self.action == "contest":
            return [IsStaff(), IsReservationsWriter()]
        return [IsStaff()]

    def get_queryset(self) -> QuerySet[OwnerBlockUpdate]:
        user = cast("User", self.request.user)
        seen = OwnerBlockUpdateSeen.objects.filter(update=OuterRef("pk"), user=user)
        return (
            OwnerBlockUpdate.objects.select_related("block", "block__property")
            .annotate(is_seen=Exists(seen))
            # Unseen first (False sorts before True), then newest — staff see
            # what they haven't acknowledged at the top.
            .order_by("is_seen", "-created_at")
        )

    def list(self, request: Request) -> Response:
        user = cast("User", request.user)
        qs = self.get_queryset()
        seen_param = request.query_params.get("seen")
        if seen_param is not None:
            # Filter via the relation (not the annotation) so the unique
            # (update, user) seen mark resolves cleanly; the annotation is
            # still carried for serialization + ordering.
            if seen_param.lower() == "true":
                qs = qs.filter(seen_marks__user=user)
            else:
                qs = qs.exclude(seen_marks__user=user)
        property_id = request.query_params.get("property")
        if property_id:
            qs = qs.filter(block__property_id=property_id)
        page = self.paginate_queryset(cast("Any", qs))
        ser = self.get_serializer(page if page is not None else qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)

    def _serialized(self, pk: str | None) -> dict[str, Any]:
        assert pk is not None  # detail routes always carry a pk
        return self.get_serializer(self.get_queryset().get(pk=pk)).data

    @action(detail=True, methods=["post"], url_path="seen")
    def seen(self, request: Request, pk: str | None = None) -> Response:
        update = get_object_or_404(OwnerBlockUpdate, pk=pk)
        OwnerBlockService.mark_seen(update, user=cast("User", request.user))
        return Response(self._serialized(pk))

    @action(detail=True, methods=["post"], url_path="unseen")
    def unseen(self, request: Request, pk: str | None = None) -> Response:
        update = get_object_or_404(OwnerBlockUpdate, pk=pk)
        OwnerBlockUpdateSeen.objects.filter(update=update, user=cast("User", request.user)).delete()
        return Response(self._serialized(pk))

    @action(detail=True, methods=["post"], url_path="contest")
    def contest(self, request: Request, pk: str | None = None) -> Response:
        update = get_object_or_404(OwnerBlockUpdate.objects.select_related("block"), pk=pk)
        payload = OwnerBlockContestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user = cast("User", request.user)
        OwnerBlockService.contest(update.block, actor=user, reason=payload.validated_data["reason"])
        # Contesting something means you've seen it.
        OwnerBlockService.mark_seen(update, user=user)
        return Response(self._serialized(pk))
