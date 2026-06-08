"""Villa Collective Django project.

Importing the Celery app here ensures it is loaded and configured whenever
Django starts, so ``@shared_task``-decorated functions share the same app and
``.delay()`` works everywhere.
"""

from __future__ import annotations

from .celery import app as celery_app

__all__ = ("celery_app",)
