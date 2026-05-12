"""Views for `TermsVersion` — list/create/detail/publish."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from rest_framework import generics, status, views
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.api import IsStaffRoleAdmin
from reservations.models.terms import TermsVersion
from reservations.serializers.terms import TermsVersionSerializer

if TYPE_CHECKING:
    from rest_framework.request import Request


class TermsVersionListCreateView(generics.ListCreateAPIView):
    """`GET / POST /terms-versions`."""

    queryset = TermsVersion.objects.all()
    serializer_class = TermsVersionSerializer
    permission_classes = [IsStaffRoleAdmin]


class TermsVersionCurrentView(generics.RetrieveAPIView):
    """`GET /terms-versions/current` — single row with `is_current=True`."""

    serializer_class = TermsVersionSerializer
    permission_classes = [AllowAny]

    def get_object(self) -> TermsVersion:
        from rest_framework.exceptions import NotFound

        instance = TermsVersion.objects.filter(is_current=True).first()
        if instance is None:
            raise NotFound("No current terms version is published.")
        return instance


class TermsVersionDetailView(generics.RetrieveAPIView):
    """`GET /terms-versions/{version}` — lookup by version slug."""

    serializer_class = TermsVersionSerializer
    permission_classes = [IsStaffRoleAdmin]
    lookup_field = "version"

    def get_queryset(self) -> Any:
        return TermsVersion.objects.all()


class TermsVersionPublishView(views.APIView):
    """`POST /terms-versions/{version}:publish`."""

    permission_classes = [IsStaffRoleAdmin]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = get_object_or_404(TermsVersion, version=self.kwargs["version"])
        instance.publish()
        return Response(TermsVersionSerializer(instance).data, status=status.HTTP_200_OK)
