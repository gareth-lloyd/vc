"""Test settings — used by pytest and CI."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from core.logging.config import configure_structlog

from .base import *  # noqa: F403

# ImageField writes (e.g. PropertyFactory's hero image) are not rolled back
# with the test transaction, so without this they accumulate in the source
# tree. Park them in a throwaway temp dir instead.
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="villa-test-media-"))

# Concurrent git worktrees share one Postgres instance (docker-compose `db`),
# so a *linked* worktree must not share the default `test_villacollective`
# database with the main checkout, or their CREATE/DROP DATABASE calls collide.
# Give each linked worktree a stable, distinct test DB name derived from its
# checkout path. A linked worktree's repo-root `.git` is a file (a gitdir
# pointer); the main checkout's and a CI clone's `.git` is a directory, so both
# keep the plain name. PYTEST_DB_SUFFIX overrides for manual control.
_db_suffix = os.environ.get("PYTEST_DB_SUFFIX")
if _db_suffix is None and (BASE_DIR.parent / ".git").is_file():  # noqa: F405 — linked worktree
    _db_suffix = hashlib.sha1(str(BASE_DIR).encode()).hexdigest()[:8]  # noqa: F405
if _db_suffix:
    DATABASES["default"]["TEST"] = {"NAME": f"test_villacollective_{_db_suffix}"}  # noqa: F405

DEBUG = False
SECRET_KEY = "test-insecure-key"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# EMAIL_BACKEND inherits locmem from base. Tests opt the dispatch gate open
# so `_send` reaches `message.send()` and fills `django.core.mail.outbox`.
# The cast-iron protection in tests is the locmem backend itself — no socket
# is ever opened — so flipping the flag here cannot leak real mail.
EMAIL_REAL_SENDS_ALLOWED = True

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Mirror base ordering: RequestMiddleware just outside AuditMiddleware, so
    # request-lifecycle logging + correlation-id adoption fire under pytest too.
    "django_structlog.middlewares.RequestMiddleware",
    "core.middleware.AuditMiddleware",
    # Mirror base: enforcement is a no-op unless a test opts in with
    # override_settings(TFA_ENFORCED=True), but it must be installed to run.
    "accounts.middleware.TfaEnforcementMiddleware",
]

# Tests exercise the seed_dev command; the guardrail must allow it here.
SEED_DEV_ALLOWED = True

# Zoho Flow push: hard-disable every kind (mirrors the EMAIL_BACKEND-style
# fail-closed override) so a developer's populated .env can never make the
# suite POST factory PII to the sandbox CRM. Tests opt in per-case with
# `override_settings(ZOHO_FLOW_WEBHOOKS=...)`.
ZOHO_FLOW_WEBHOOKS = {"contact": "", "enquiry": "", "quote": "", "booking": ""}

ENVIRONMENT = "test"
# Console renderer (no colour, no JSON) keeps pytest output readable, and
# cache_logger_on_first_use=False is required for `structlog.testing.capture_logs`
# to intercept already-imported module-level loggers.
LOG_JSON = False
LOGGING = configure_structlog(json_logs=False, level="WARNING", cache=False, console_colors=False)

# Celery: run tasks inline (no broker, no worker) and re-raise task exceptions
# so `.delay(...)` behaves synchronously in tests. The in-memory broker URL
# means nothing tries to reach Redis even when a task is invoked directly.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"

# The suite logs in dozens of times per process against the shared locmem
# throttle cache — relax the auth rates so legitimate test traffic never
# trips them. The dedicated throttle tests override these with tight rates.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "auth.login": "10000/min",
        "auth.tfa": "10000/min",
        "auth.password_reset": "10000/min",
    },
}
