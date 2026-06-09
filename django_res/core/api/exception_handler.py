"""Canonical DRF exception handler.

Normalises every error response to a problem-detail style payload:

    {"code": "<machine_code>", "detail": "<message>", "field_errors": {...}}

`field_errors` is present (possibly empty) only for ValidationError.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.db.models.deletion import ProtectedError, RestrictedError
from rest_framework import exceptions, status
from rest_framework.response import Response

from core.exceptions import DomainError

logger = structlog.get_logger("api")


def _log_handled_error(exc: Exception, context: dict[str, Any]) -> None:
    """Log a 4xx we mapped from an otherwise-unhandled exception.

    Only for errors we *convert to a Response* (domain conflicts, PROTECT/
    RESTRICT) — DRF's own 4xx (ValidationError etc.) are routine client errors
    not worth a line, and genuinely *unhandled* exceptions (→500) are already
    logged as `request_failed` by django-structlog's RequestMiddleware via
    `got_request_exception`; logging them here too would double every 500.
    `request_id`/`user_id` are bound by that middleware, so they ride along.
    """
    request = context.get("request")
    view = context.get("view")
    logger.warning(
        "api.request_failed",
        exc_type=type(exc).__name__,
        error=str(exc),
        view=type(view).__name__ if view is not None else None,
        method=getattr(request, "method", None),
        path=getattr(request, "path", None),
    )


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
        _log_handled_error(exc, context)
        return Response(
            {
                "code": getattr(exc, "code", "domain_error"),
                "detail": str(exc) or "Domain error",
                # A domain error may carry per-field messages (e.g. a malformed
                # template names the offending field); surface them in the
                # canonical slot rather than a bespoke top-level key.
                "field_errors": getattr(exc, "field_errors", None) or {},
            },
            status=getattr(exc, "status_code", status.HTTP_409_CONFLICT),
        )

    # A delete blocked by an on_delete=PROTECT / RESTRICT foreign key is a
    # "state refused this operation" conflict, not a server fault. DRF leaves
    # these DB-layer exceptions unhandled (→ 500), so map them to 409 here.
    if isinstance(exc, (ProtectedError, RestrictedError)):
        _log_handled_error(exc, context)
        return Response(
            {
                "code": "protected",
                "detail": str(exc) or "Cannot delete: record is still referenced.",
                "field_errors": {},
            },
            status=status.HTTP_409_CONFLICT,
        )

    # Imported lazily: `core.api` is referenced by `DEFAULT_PERMISSION_CLASSES`,
    # so eagerly importing `rest_framework.views` here would trip a circular
    # import while DRF is still initialising that module.
    from rest_framework.views import exception_handler as drf_default_handler

    response = drf_default_handler(exc, context)
    if response is None:
        # DRF couldn't map it → this becomes a 500. Don't log here: Django fires
        # `got_request_exception` on the re-raise and django-structlog's
        # RequestMiddleware already logs it as `request_failed` (with traceback).
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
