"""`GET /roles` — read-only enum listing for the StaffRole dropdown."""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.enums import StaffRole


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def role_list(request: Request) -> Response:
    """Return the fixed `StaffRole` choices.

    Roles are a closed enum in code, so this endpoint is non-paginated and
    has no write counterpart. It exists to populate `?role=` filters and the
    user-edit dropdown without hard-coding the values in the SPA.
    """
    return Response([{"value": value, "label": label} for value, label in StaffRole.choices])
