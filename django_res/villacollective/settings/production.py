"""Production settings — Render."""

from __future__ import annotations

from .base import *  # noqa: F403
from .base import env

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
