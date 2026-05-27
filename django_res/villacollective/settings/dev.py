"""Local development settings."""

from __future__ import annotations

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# Local dev may seed fake data (see core/management/commands/seed_dev.py).
SEED_DEV_ALLOWED = True

# Email safety: dev intentionally inherits both gates from base
# (EMAIL_BACKEND=locmem, EMAIL_REAL_SENDS_ALLOWED=False). Do not override.
# To inspect outgoing mail, read `EmailLog` rows or `django.core.mail.outbox`.
