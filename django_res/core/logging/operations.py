"""``log_operation`` — a uniform start/succeed/fail wrapper for fallible work.

A service operation, a webhook handler, or a batch job is a *fallible verb*:
it either succeeds or raises. ``log_operation`` gives every such verb the same
shape of log line so dashboards and queries are uniform:

- ``<event>.started`` (``debug``, opt-in) — before the work runs.
- ``<event>.succeeded`` (``info``) — with ``duration_ms``.
- ``<event>.failed`` (``error`` + traceback) — with ``duration_ms`` and the
  exception, then **re-raises**. The wrapper never swallows.

The fields you pass are bound into ``structlog.contextvars`` for the duration,
so *nested* log lines emitted inside the block inherit them too, and they're
unwound cleanly on exit. The context manager yields a **mutable dict** — mutate
it to attach ids discovered mid-operation (e.g. a row's pk after ``create``) so
they land on the ``.succeeded`` line:

    with log_operation("refund.request", logger=logger, booking_id=booking.pk) as ctx:
        refund = Refund.objects.create(...)
        ctx["refund_id"] = refund.pk          # rides on refund.request.succeeded
        return refund

``logger`` is required: pass the module's ``structlog.get_logger(__name__)`` so
the events keep their origin (``logger="payments.services.refund"``) and stay
searchable alongside the module's other lines. Only wrap *fallible operations*
— input/permission validation that rejects bad calls belongs *above* the block
(a rejected request is not an operation failure), and a bare fact already true
(``booking.created``) stays a single event, not a triple.

Conventions (see ``django_res/CLAUDE.md`` §"Structured logging"): dotted
lowercase ``domain.action`` event base, money as ``str(Decimal)``, and never
bind a reserved key (``message``/``level``/``status`` or the auto-bound
``request_id``/``user_id``/``correlation_id``/``service``/``env``/``release``).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog


def _duration_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


@contextmanager
def log_operation(
    event: str,
    *,
    logger: Any,
    emit_started: bool = False,
    **fields: Any,
) -> Iterator[dict[str, Any]]:
    """Time a fallible block; emit ``<event>.succeeded`` / ``.failed``.

    ``fields`` are bound into structlog contextvars (so nested lines inherit
    them) and stamped on the start/success/failure lines. Yields a mutable dict
    — add to it to enrich the ``.succeeded`` line with ids found mid-operation.
    Re-raises on failure.
    """
    ctx: dict[str, Any] = dict(fields)
    tokens = structlog.contextvars.bind_contextvars(**fields)
    start = time.perf_counter()
    try:
        if emit_started:
            logger.debug(f"{event}.started", **ctx)
        yield ctx
    except Exception as exc:
        logger.exception(
            f"{event}.failed",
            duration_ms=_duration_ms(start),
            error=str(exc),
            **ctx,
        )
        raise
    else:
        logger.info(f"{event}.succeeded", duration_ms=_duration_ms(start), **ctx)
    finally:
        structlog.contextvars.reset_contextvars(**tokens)
