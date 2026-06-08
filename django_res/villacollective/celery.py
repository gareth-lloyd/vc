"""Celery application object.

Imported by ``villacollective/__init__.py`` so the app is configured on every
Django startup (web, worker, beat, shell). Config lives in Django settings under
the ``CELERY_`` namespace (``settings/base.py``); tasks are auto-discovered from
each app's ``tasks.py``.
"""

from __future__ import annotations

import os

from celery import Celery

# A sensible default for ad-hoc invocations (`celery -A villacollective ...`)
# without DJANGO_SETTINGS_MODULE exported. Real environments set it explicitly
# (render.yaml, pytest, manage.py).
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "villacollective.settings.dev")

app = Celery("villacollective")

# Pull every CELERY_-prefixed setting (e.g. CELERY_BROKER_URL -> broker_url).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Import <app>/tasks.py for every app in INSTALLED_APPS so @shared_task
# functions register at worker startup.
app.autodiscover_tasks()
