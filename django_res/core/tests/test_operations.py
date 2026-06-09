"""Behavioural tests for ``log_operation``.

We deliberately do *not* assert on the emitted log lines (that the
``.succeeded`` event fires with ``duration_ms`` etc.) — those just restate the
implementation and add brittle, low-value coverage. What's worth pinning is the
*behaviour* a bug could silently break:

- the context manager **re-raises** (it must never swallow), and
- it **cleans up the contextvars** it bound, on both the success and failure
  paths, so operation-scoped fields don't leak into later log lines.
"""

from __future__ import annotations

import pytest
import structlog

from core.logging.operations import log_operation

_log = structlog.get_logger("test")


def test_reraises_and_unbinds_on_failure() -> None:
    structlog.contextvars.clear_contextvars()

    with pytest.raises(ValueError, match="boom"):
        with log_operation("widget.build", logger=_log, widget_id=7):
            assert structlog.contextvars.get_contextvars()["widget_id"] == 7
            raise ValueError("boom")

    # The bound field must not survive the failed block.
    assert "widget_id" not in structlog.contextvars.get_contextvars()


def test_unbinds_on_success() -> None:
    structlog.contextvars.clear_contextvars()

    with log_operation("widget.build", logger=_log, widget_id=7):
        assert structlog.contextvars.get_contextvars()["widget_id"] == 7

    assert "widget_id" not in structlog.contextvars.get_contextvars()


def test_ctx_mutation_is_visible_to_caller() -> None:
    """The yielded dict is the lever for attaching ids found mid-operation."""
    structlog.contextvars.clear_contextvars()

    with log_operation("widget.build", logger=_log) as ctx:
        ctx["widget_id"] = 7

    assert ctx == {"widget_id": 7}


def test_restores_outer_binding_rather_than_deleting() -> None:
    """A nested operation must restore the outer value, not wipe the key."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(widget_id="outer")

    with log_operation("widget.build", logger=_log, widget_id="inner"):
        assert structlog.contextvars.get_contextvars()["widget_id"] == "inner"

    assert structlog.contextvars.get_contextvars()["widget_id"] == "outer"
    structlog.contextvars.clear_contextvars()
