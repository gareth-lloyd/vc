"""GET /owner/me — owner identity, organisations, per-property visibility."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers.auth import UserMeSerializer
from owners.enums import OwnerMembershipStatus, OwnerOrgStatus
from owners.models import OwnerMembership, OwnerOrgProperty

if TYPE_CHECKING:
    from rest_framework.request import Request

    from accounts.models import User


class OwnerMeView(APIView):
    """Owner counterpart to `/auth/me` + `/auth/permissions`.

    The SPA probes this at boot to pick its shell, so it must not signal a
    routing decision with an error status. Gated by `IsAuthenticated` only:
    anonymous callers are rejected, but an authenticated non-owner gets a
    plain `200 {is_owner: false, organisations: []}` (no console 403). An
    owner gets `is_owner: true` plus their orgs (ACTIVE membership of an
    ACTIVE org), their role in each, and the open per-property visibility
    grants. The owner *data* endpoints (`/owner/properties`, …) keep `IsOwner`
    — this probe leaks nothing, so it can stay readable.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast("User", request.user)
        memberships = list(
            OwnerMembership.objects.filter(
                user=user,
                status=OwnerMembershipStatus.ACTIVE,
                organisation__status=OwnerOrgStatus.ACTIVE,
            ).select_related("organisation")
        )
        if not memberships:
            # Not an owner — identical predicate to owners.permissions.is_owner.
            return Response(
                {"user": UserMeSerializer(user).data, "is_owner": False, "organisations": []}
            )
        org_ids = [m.organisation_id for m in memberships]

        grants_by_org: dict[int, list[dict[str, object]]] = {oid: [] for oid in org_ids}
        for grant in OwnerOrgProperty.objects.filter(
            organisation_id__in=org_ids, end_date__isnull=True
        ).values("organisation_id", "property_id", "view_full_money", "view_guest_details"):
            grants_by_org[grant["organisation_id"]].append(
                {
                    "property_id": grant["property_id"],
                    "view_full_money": grant["view_full_money"],
                    "view_guest_details": grant["view_guest_details"],
                }
            )

        organisations = [
            {
                "id": m.organisation_id,
                "name": m.organisation.name,
                "role": m.role,
                "properties": grants_by_org[m.organisation_id],
            }
            for m in memberships
        ]
        return Response(
            {
                "user": UserMeSerializer(user).data,
                "is_owner": True,
                "organisations": organisations,
            }
        )
