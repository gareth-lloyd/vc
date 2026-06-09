"""Enrich django-structlog's Celery task lifecycle with ``task_name``.

django-structlog's worker bootstep (wired in ``villacollective/celery.py``)
already binds ``task_id`` and emits ``task_succeeded`` / ``task_failed`` /
``task_retrying`` for every task run. The one thing it omits from the bound
context is the task's *name*, which is what you actually filter on in a log
search ("show me failures of ``reservations.tasks.expire_holds``").

``bind_extra_task_metadata`` is django-structlog's sanctioned hook for adding
fields to that auto-bound context without touching individual tasks — so this
single receiver enriches every task at once. Imported for its side effect from
``villacollective/celery.py`` (after the bootstep registration); the
``@receiver`` connection happens at import time.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.dispatch import receiver
from django_structlog.celery import signals


@receiver(signals.bind_extra_task_metadata)
def add_task_name(sender: Any, task: Any = None, **kwargs: Any) -> None:
    """Bind the running task's dotted name into structlog contextvars."""
    if task is not None:
        structlog.contextvars.bind_contextvars(task_name=task.name)
