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

# Media (PropertyImage / Collection.cover_image) lives in S3, not on Render's
# ephemeral disk. Objects are world-readable via the bucket policy, so URLs
# are plain unsigned `https://villacollective-images.s3.…/<location>/<key>`
# (querystring_auth off). Credentials come from the standard boto3 env vars
# (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY) set per Render service. ACLs are
# blocked on the bucket — default_acl must stay None. See
# django_res_design/todo/gap-012-s3-image-hosting.md.
S3_STORAGE_OPTIONS: dict[str, object] = {
    "bucket_name": "villacollective-images",
    "region_name": "eu-central-1",
    # Env prefix inside the shared bucket; staging.py overrides.
    "location": "production",
    "querystring_auth": False,
    "default_acl": None,
    # Never clobber an existing object — collide → auto-suffix.
    "file_overwrite": False,
}
STORAGES["default"] = {  # noqa: F405
    "BACKEND": "storages.backends.s3.S3Storage",
    "OPTIONS": S3_STORAGE_OPTIONS,
}
