"""Unit tests for static-field, noise-drop and Datadog-mapping processors."""

from __future__ import annotations

from typing import Any

import pytest
import structlog

from core.logging import processors
from core.logging.processors import add_static_fields, drop_noisy_requests, level_to_status


def test_static_fields_added(settings: Any) -> None:
    settings.ENVIRONMENT = "test-env"
    settings.RELEASE_VERSION = "abc123"
    processors._service_static = None  # reset the lazy cache for this test
    out = add_static_fields(None, "info", {"event": "x"})
    assert out["service"] == "villacollective-api"
    assert out["env"] == "test-env"
    assert out["release"] == "abc123"
    processors._service_static = None  # don't leak into other tests


def test_static_fields_do_not_override_explicit() -> None:
    processors._service_static = {"service": "s", "env": "e", "release": "r"}
    out = add_static_fields(None, "info", {"event": "x", "env": "explicit"})
    assert out["env"] == "explicit"
    processors._service_static = None


@pytest.mark.parametrize(
    "request_line",
    ["GET /api/health/", "GET /api/health", "GET /static/app.js", "GET /media/x.jpg?v=2"],
)
def test_noisy_request_paths_are_dropped(request_line: str) -> None:
    with pytest.raises(structlog.DropEvent):
        drop_noisy_requests(None, "info", {"event": "request_finished", "request": request_line})


def test_normal_request_path_passes() -> None:
    event = {"event": "request_finished", "request": "GET /api/v1/payments", "code": 200}
    assert drop_noisy_requests(None, "info", event) is event


def test_non_request_events_are_never_dropped() -> None:
    # A domain event that merely mentions a health-ish path must not be dropped.
    event = {"event": "refund.requested", "request": "GET /api/health/"}
    assert drop_noisy_requests(None, "info", event) is event


def test_level_renamed_to_status() -> None:
    out = level_to_status(None, "info", {"event": "x", "level": "warning"})
    assert out["status"] == "warning"
    assert "level" not in out


def test_domain_status_kwarg_is_preserved_not_clobbered() -> None:
    # A caller that used the reserved `status` key for a domain value keeps it
    # under `status_`; severity still wins the `status` facet.
    out = level_to_status(None, "info", {"event": "x", "level": "info", "status": "DRAFT"})
    assert out["status"] == "info"
    assert out["status_"] == "DRAFT"
