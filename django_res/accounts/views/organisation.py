"""Organisation CRUD + :merge (GAP-046).

The B2B "Companies" API. Screens are `org_type`-scoped (the Companies
directory filters `org_type=agency`); the viewset itself serves every type so
GAP-048 (management companies) and q-007 (suppliers) reuse it.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import filters, status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import Organisation
from accounts.serializers import OrganisationMergeSerializer, OrganisationSerializer
from core.api import IsStaff, IsStaffRoleAdmin


class OrganisationFilterSet(FilterSet):
    class Meta:
        model = Organisation
        fields = {
            "org_type": ["exact"],
            "status": ["exact"],
        }


class OrganisationViewSet(viewsets.ModelViewSet[Organisation]):
    """`/organisations` — agencies, management companies, suppliers."""

    queryset = Organisation.objects.all()
    serializer_class = OrganisationSerializer
    permission_classes = [IsStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrganisationFilterSet
    search_fields = ["name", "email"]
    ordering_fields = ["name", "created_at"]


class OrganisationMergeView(viewsets.ViewSet):
    """`POST /organisations/{id}:merge` — delegates to `Organisation.merge(target)`.

    Destructive (repoints the source's agents onto the target, then hard-deletes
    the source) so we gate on `IsStaffRoleAdmin`.
    """

    permission_classes = [IsStaffRoleAdmin]

    def create(self, request: Request, pk: str | None = None) -> Response:
        source = get_object_or_404(Organisation, pk=pk)
        serializer = OrganisationMergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_id = serializer.validated_data["target_organisation_id"]
        target = get_object_or_404(Organisation, pk=target_id)
        try:
            source.merge(target)
        except ValueError as exc:
            return Response(
                {"code": "merge_invalid", "detail": str(exc), "field_errors": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(OrganisationSerializer(target).data, status=status.HTTP_200_OK)
