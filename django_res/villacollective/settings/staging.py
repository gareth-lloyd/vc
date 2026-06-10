"""Staging settings — Render. Production-equivalent security, seeding allowed."""

from __future__ import annotations

import os

from django.core.exceptions import ImproperlyConfigured

# Staging-only ALLOWED_HOSTS default. production.py reads the env var with no
# default (fail-fast for real prod), and it does so *during* the star-import
# below — so an ordinary `ALLOWED_HOSTS = ...` override here would never run.
# Defaulting the env var first keeps prod strict while letting every Render
# staging service (web, worker, beat) boot without declaring it. An explicitly
# set env var still wins.
os.environ.setdefault("ALLOWED_HOSTS", ".onrender.com")

from .base import env
from .production import *  # noqa: F403

ENVIRONMENT = "staging"

# Staging is a throwaway demo DB — realistic fake data is expected here.
# (Mirrors the explicit SEED_DEV_ALLOWED toggle in dev.py / test.py.)
SEED_DEV_ALLOWED = True

# Media goes to the shared S3 bucket (config inherited from production.py)
# under the staging/ prefix, so the two envs never collide on a key.
S3_STORAGE_OPTIONS["location"] = "staging"  # noqa: F405

# Email safety: staging opens the SMTP gates inherited from production but
# requires an explicit recipient allowlist so a stray send can never reach a
# real guest. Boot-time guard refuses to start with real SMTP + empty list.
EMAIL_RECIPIENT_ALLOWLIST = env.list("EMAIL_RECIPIENT_ALLOWLIST", default=[])

if not EMAIL_RECIPIENT_ALLOWLIST:
    raise ImproperlyConfigured(
        "Staging requires EMAIL_RECIPIENT_ALLOWLIST to be set. "
        "Refusing to start with an empty allowlist + real SMTP backend."
    )

# Staging runs no Celery worker/beat services (pointless expense for a demo
# box) — tasks execute inline in the web process, same as test.py. The
# trade-offs are acceptable here: SMTP sends add latency to the request that
# triggers them, and beat's periodic sweeps (hold expiry, payment reminders,
# iCal ingest, auto check-out) simply don't run.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
