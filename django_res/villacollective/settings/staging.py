"""Staging settings — Render. Production-equivalent security, seeding allowed."""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from .base import env
from .production import *  # noqa: F403

ENVIRONMENT = "staging"

# Staging is a throwaway demo DB — realistic fake data is expected here.
# (Mirrors the explicit SEED_DEV_ALLOWED toggle in dev.py / test.py.)
SEED_DEV_ALLOWED = True

# Email safety: staging opens the SMTP gates inherited from production but
# requires an explicit recipient allowlist so a stray send can never reach a
# real guest. Boot-time guard refuses to start with real SMTP + empty list.
EMAIL_RECIPIENT_ALLOWLIST = env.list("EMAIL_RECIPIENT_ALLOWLIST", default=[])

if not EMAIL_RECIPIENT_ALLOWLIST:
    raise ImproperlyConfigured(
        "Staging requires EMAIL_RECIPIENT_ALLOWLIST to be set. "
        "Refusing to start with an empty allowlist + real SMTP backend."
    )
