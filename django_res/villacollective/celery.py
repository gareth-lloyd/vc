"""Celery application object.

Imported by ``villacollective/__init__.py`` so the app is configured on every
Django startup (web, worker, beat, shell). Config lives in Django settings under
the ``CELERY_`` namespace (``settings/base.py``); tasks are auto-discovered from
each app's ``tasks.py``.
"""

from __future__ import annotations

import os

from celery import Celery
from django_structlog.celery.steps import DjangoStructLogInitStep

# A sensible default for ad-hoc invocations (`celery -A villacollective ...`)
# without DJANGO_SETTINGS_MODULE exported. Real environments set it explicitly
# (render.yaml, pytest, manage.py).
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "villacollective.settings.dev")

app = Celery("villacollective")

# Pull every CELERY_-prefixed setting (e.g. CELERY_BROKER_URL -> broker_url).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Worker-side half of django-structlog's Celery integration: this bootstep
# connects the task-lifecycle signal receivers so each task run binds
# `task_id` (and the publisher's `request_id`, carried on the message headers)
# into structlog's contextvars. The publisher-side half — stamping those
# headers when a task is enqueued — is switched on by
# DJANGO_STRUCTLOG_CELERY_ENABLED in settings. Both are needed for request_id
# to survive the publish→consume boundary.
app.steps["worker"].add(DjangoStructLogInitStep)

# Side-effect import: connects the `bind_extra_task_metadata` receiver that
# adds `task_name` to every task's auto-bound structlog context. Must follow
# the bootstep registration above (it builds on django-structlog's signals).
import core.logging.celery  # noqa: E402,F401

# Import <app>/tasks.py for every app in INSTALLED_APPS so @shared_task
# functions register at worker startup.
app.autodiscover_tasks()
