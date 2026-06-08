"""structlog + stdlib ``logging`` wiring, shared by all settings modules.

One ``configure_structlog`` call per settings module returns the ``LOGGING``
dict *and* configures structlog itself, so structlog-native loggers and plain
``logging.getLogger`` calls render through one pipeline:

- The **shared pre-chain** (contextvars, static fields, level, timestamp,
  redaction, noise-drop) runs for both structlog and foreign stdlib records.
- The **render stage** turns the event dict into a line — JSON for
  staging/production (with Datadog ``message``/``status`` mapping) or a pretty
  console line for dev/test.

Calling it as a function (rather than executing config at import) lets each
environment pass the right ``json_logs``/``cache`` without re-declaring the
processor chain — notably ``cache=False`` under test, where
``cache_logger_on_first_use=True`` would defeat ``structlog.testing.capture_logs``.
"""

from __future__ import annotations

from typing import Any

import structlog

from core.logging.processors import add_static_fields, drop_noisy_requests, level_to_status
from core.logging.redaction import redact_sensitive


def _shared_processors() -> list[Any]:
    """Pre-render chain applied to every record (structlog + foreign stdlib)."""
    return [
        structlog.contextvars.merge_contextvars,
        # Drop health/static request spam first, before any timestamp/redaction
        # work — these are the highest-frequency events and would otherwise pay
        # the full chain only to be discarded.
        drop_noisy_requests,
        add_static_fields,
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_sensitive,
    ]


def configure_structlog(
    *, json_logs: bool, level: str = "INFO", cache: bool = True, console_colors: bool = True
) -> dict[str, Any]:
    """Configure structlog and return the Django ``LOGGING`` dict."""
    shared = _shared_processors()

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=cache,
    )

    if json_logs:
        render_chain: list[Any] = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            # Datadog reserves `message` (log body) and `status` (severity);
            # structlog defaults to `event`/`level`, so remap both here.
            structlog.processors.EventRenamer("message"),
            level_to_status,
            structlog.processors.JSONRenderer(),
        ]
    else:
        render_chain = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=console_colors),
        ]

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structured": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": render_chain,
                "foreign_pre_chain": shared,
            },
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "structured"},
        },
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            # django.server's per-request access line duplicates django-structlog's
            # `request_finished`; quiet it so we don't log every request twice.
            "django.server": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        },
    }
