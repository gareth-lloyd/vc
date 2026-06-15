"""Request-lifecycle logging + request_id/correlation_id unification."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import structlog
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from structlog.testing import capture_logs

from core.middleware import AuditMiddleware
from core.request_context import get_correlation_id


@pytest.fixture(autouse=True)
def _clean_contextvars() -> Iterator[None]:
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()


def _run_middleware(rf: Any) -> dict[str, Any]:
    """Drive AuditMiddleware once; capture the correlation id seen by the view."""
    seen: dict[str, Any] = {}

    def get_response(request: Any) -> HttpResponse:
        seen["correlation_id"] = get_correlation_id()
        seen["bound"] = structlog.contextvars.get_contextvars().get("correlation_id")
        return HttpResponse("ok")

    request = rf.get("/api/v1/payments")
    request.user = AnonymousUser()
    AuditMiddleware(get_response)(request)
    return seen


def test_audit_middleware_adopts_request_id_as_correlation_id(rf: Any) -> None:
    request_id = uuid.uuid4()
    structlog.contextvars.bind_contextvars(request_id=str(request_id))

    seen = _run_middleware(rf)

    assert seen["correlation_id"] == request_id
    # The contextvar alias matches the audit correlation id exactly.
    assert seen["bound"] == str(request_id)


def test_audit_middleware_mints_when_no_request_id(rf: Any) -> None:
    seen = _run_middleware(rf)
    assert isinstance(seen["correlation_id"], uuid.UUID)


def test_audit_middleware_falls_back_on_non_uuid_request_id(rf: Any) -> None:
    structlog.contextvars.bind_contextvars(request_id="not-a-uuid")
    seen = _run_middleware(rf)
    # A non-UUID inbound id is ignored; a fresh UUID is minted instead.
    assert isinstance(seen["correlation_id"], uuid.UUID)


@pytest.mark.django_db
def test_request_lifecycle_events_emitted(client: Any) -> None:
    with capture_logs() as logs:
        # Unauthenticated staff API call → 403, but the full middleware stack
        # (incl. RequestMiddleware) still runs and logs the lifecycle.
        client.get("/api/v1/payments")

    events = [entry.get("event") for entry in logs]
    assert "request_started" in events

    finished = [e for e in logs if e.get("event") == "request_finished"]
    assert finished, "expected a request_finished event"
    assert finished[-1]["code"] in (401, 403)
