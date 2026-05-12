"""Canonical DRF exception handler.

Normalises every error response to a problem-detail style payload:

    {"code": "<machine_code>", "detail": "<message>", "field_errors": {...}}

`field_errors` is present (possibly empty) only for ValidationError.
"""

from __future__ import annotations

from typing import Any

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

from core.exceptions import DomainError


def _code_for(exc: Exception) -> str:
    default_code = getattr(exc, "default_code", None)
    if isinstance(default_code, str):
        return default_code
    return type(exc).__name__.lower()


def canonical_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Wrap DRF exceptions in our canonical `{code, detail, field_errors}` shape.

    Domain errors (subclasses of `core.exceptions.DomainError`) are mapped to
    HTTP 409 with the typed `code` attribute so callers can branch on a stable
    machine-readable identifier.
    """
    if isinstance(exc, DomainError):
        return Response(
            {
                "code": getattr(exc, "code", "domain_error"),
                "detail": str(exc) or "Domain error",
                "field_errors": {},
            },
            status=getattr(exc, "status_code", status.HTTP_409_CONFLICT),
        )

    response = drf_default_handler(exc, context)
    if response is None:
        return None

    data = response.data
    field_errors: dict[str, Any] = {}
    detail: str

    if isinstance(exc, exceptions.ValidationError):
        if isinstance(data, dict):
            field_errors = dict(data)
            detail = "Validation failed"
        elif isinstance(data, list):
            detail = "; ".join(str(item) for item in data) or "Validation failed"
        else:
            detail = str(data) or "Validation failed"
        code = "validation_error"
    else:
        if isinstance(data, dict) and "detail" in data:
            detail = str(data["detail"])
        else:
            detail = str(data) if data else exc.__class__.__name__
        code = _code_for(exc)

    response.data = {"code": code, "detail": detail, "field_errors": field_errors}
    return response
