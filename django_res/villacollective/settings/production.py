"""Production settings — Render."""

from __future__ import annotations

from .base import *  # noqa: F403
from .base import env

ENVIRONMENT = "production"

DEBUG = False
SECRET_KEY = env.str("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
# Single-origin deploy (Django serves the SPA) — no CORS. Django >=4 still
# requires the HTTPS origin trusted for unsafe session-auth POSTs.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Email safety: production is the only environment that opens both gates.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_REAL_SENDS_ALLOWED = True
# EMAIL_RECIPIENT_ALLOWLIST stays empty (inherited) — no restriction in prod.
