"""Test settings — used by pytest and CI."""

from __future__ import annotations

import tempfile

from .base import *  # noqa: F403

# ImageField writes (e.g. PropertyFactory's hero image) are not rolled back
# with the test transaction, so without this they accumulate in the source
# tree. Park them in a throwaway temp dir instead.
MEDIA_ROOT = tempfile.mkdtemp(prefix="villa-test-media-")

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
    "core.middleware.AuditMiddleware",
]

# Tests exercise the seed_dev command; the guardrail must allow it here.
SEED_DEV_ALLOWED = True
