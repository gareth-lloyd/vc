"""Custom structlog processors: static fields, noise control, Datadog mapping."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from structlog.types import EventDict, WrappedLogger

# Request paths whose lifecycle logs carry no debugging value but would
# dominate volume (and Datadog ingest cost): Render health polls and any
# static / media asset served by WhiteNoise.
_NOISY_PATH_PREFIXES: tuple[str, ...] = ("/api/health", "/static/", "/media/")

# django-structlog request events whose ``request`` field we inspect.
_REQUEST_EVENTS: frozenset[str] = frozenset(
    {"request_started", "request_finished", "request_failed"}
)

_service_static: dict[str, str] | None = None


def _static_fields() -> dict[str, str]:
    """Service/env/release stamped on every line. Built once, lazily, from settings."""
    global _service_static
    if _service_static is None:
        from django.conf import settings

        _service_static = {
            "service": "villacollective-api",
            "env": getattr(settings, "ENVIRONMENT", "dev"),
            "release": getattr(settings, "RELEASE_VERSION", "dev"),
        }
    return _service_static


def add_static_fields(
    _logger: WrappedLogger, _method_name: str, event_dict: EventDict
) -> EventDict:
    """structlog processor: merge static service/env/release fields."""
    for key, value in _static_fields().items():
        event_dict.setdefault(key, value)
    return event_dict


def drop_noisy_requests(
    _logger: WrappedLogger, _method_name: str, event_dict: EventDict
) -> EventDict:
    """structlog processor: drop request lifecycle logs for health/static paths.

    django-structlog logs ``request_started``/``request_finished`` with a
    ``request`` field of the form ``"GET /api/health/"``. Raise ``DropEvent``
    for the noisy prefixes so they never reach stdout.
    """
    if event_dict.get("event") in _REQUEST_EVENTS:
        request = event_dict.get("request", "")
        if isinstance(request, str):
            # "METHOD /full/path?qs" → "/full/path"
            _, _, path = request.partition(" ")
            path = path.split("?", 1)[0]
            if path.startswith(_NOISY_PATH_PREFIXES):
                raise structlog.DropEvent
    return event_dict


def level_to_status(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    """structlog processor: map ``level`` → ``status`` for Datadog's severity facet.

    ``status`` is reserved for severity. If a caller also passed a domain
    ``status=`` kwarg it would otherwise be silently clobbered, so preserve it
    under ``status_`` rather than dropping it (the convention is to avoid the
    reserved key — this is the safety net for when it slips through).
    """
    if "level" in event_dict:
        if "status" in event_dict:
            event_dict.setdefault("status_", event_dict["status"])
        event_dict["status"] = event_dict.pop("level")
    return event_dict
