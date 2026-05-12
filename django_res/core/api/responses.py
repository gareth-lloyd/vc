"""Convenience response helpers shared across the API."""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response


def not_implemented_response(detail: str) -> Response:
    """Return a canonical 501 problem-detail response.

    Used for spec endpoints whose business wiring isn't ready in MVP (magic-link
    dispatch, admin password reset email, owner-portal invite, etc.).
    """
    return Response(
        {"code": "not_implemented", "detail": detail, "field_errors": {}},
        status=status.HTTP_501_NOT_IMPLEMENTED,
    )
