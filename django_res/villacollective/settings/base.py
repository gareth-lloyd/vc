"""Shared Django settings — all environments inherit from here."""

from __future__ import annotations

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

# Load the repo-root `.env` (BASE_DIR is `django_res/`; the env file lives one
# level up alongside docker-compose) so secrets (DATABASE_URL, OPEN_AI_API_KEY,
# …) can live there for local commands. Real environment variables still take
# precedence — read_env only fills in keys not already set in os.environ.
environ.Env.read_env(BASE_DIR.parent / ".env")

SECRET_KEY = env.str("DJANGO_SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.admin",
    "django.contrib.postgres",
    "rest_framework",
    "django_filters",
    "core",
    "accounts",
    "properties",
    "owners",
    "pricing",
    "reservations",
    "payments",
    "integrations",
    "comms",
    "data_migration",
    "seeding",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise + media: serves static assets, the SPA build, and MEDIA_ROOT.
    "core.middleware.MediaWhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "core.middleware.AuditMiddleware",
]

AUTH_USER_MODEL = "accounts.User"

ROOT_URLCONF = "villacollective.urls"
WSGI_APPLICATION = "villacollective.wsgi.application"
ASGI_APPLICATION = "villacollective.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgres://villa:villa@localhost:55432/villacollective",
    ),
}

# Legacy SQL Server access (data_migration app) is handled outside Django's
# DATABASES — see data_migration.legacy_db — to avoid the MS ODBC system
# dependency. Set LEGACY_DATABASE_URL when running loaders.

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded / seeded media (e.g. PropertyImage), stored on local
# FileSystemStorage and served by `core.middleware.MediaWhiteNoiseMiddleware`
# (which mounts MEDIA_ROOT) in every environment. The `/media/` prefix keeps
# uploads out of the SPA's root namespace so they don't collide with
# client-side routes (`/properties/:id`); `villacollective.urls` excludes
# `media/` from the SPA catch-all so a missing file 404s instead of returning
# the shell. `test` settings override MEDIA_ROOT to a throwaway temp dir.
#
# NOTE: WhiteNoise indexes files at boot; runtime-written media (a live
# `seed_dev` run, a user upload) is only served when WHITENOISE_AUTOREFRESH is
# on — default under DEBUG, enabled on staging. Production uploads at scale
# should move to remote storage (see PropertyImageWriteSerializer's signed-URL
# write path), which would replace the WhiteNoise media mount.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Single-origin SPA: the built Vite bundle is copied here by the Docker
# build. When present, WhiteNoise serves the hashed assets (far-future
# caching) and `core.spa_index` is the client-side-routing history fallback.
# Absent in a local checkout — dev serves the SPA via the Vite proxy, so the
# guard keeps base untouched.
#
# `WHITENOISE_INDEX_FILE` stays OFF (load-bearing): with it enabled,
# WhiteNoiseMiddleware serves `index.html` for `/` directly, short-circuiting
# the view layer so `core.spa_index`'s `@ensure_csrf_cookie` never fires. A
# fresh visitor to `/` then has no `csrftoken` cookie and their first login
# POST is 403'd by CsrfViewMiddleware — the recurring "log in twice" bug. With
# it off, every HTML entry point falls through to `spa_index`, which primes
# the cookie; WhiteNoise still serves `/assets/*` and the literal `/index.html`.
SPA_ROOT = BASE_DIR / "frontend_dist"
WHITENOISE_INDEX_FILE = False
if SPA_ROOT.is_dir():
    WHITENOISE_ROOT = SPA_ROOT

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    # Secure default: the staff API is staff-only. Public endpoints opt out
    # with `AllowAny`; owner-portal endpoints with `owners.permissions.IsOwner`;
    # self-service identity endpoints (`/auth/me`, logout, …) with
    # `IsAuthenticated`. Anything that forgets to declare a permission is
    # locked to staff rather than leaking to any authenticated principal.
    "DEFAULT_PERMISSION_CLASSES": [
        "core.api.permissions.IsStaff",
    ],
    "EXCEPTION_HANDLER": "core.api.exception_handler.canonical_exception_handler",
}

# App-layer Fernet encryption for TOTP secrets / SMTP passwords / OAuth tokens.
# Format: list of base64-encoded 32-byte keys; oldest decrypts, newest encrypts.
FERNET_KEYS = env.list(
    "FERNET_KEYS",
    default=["wIZ6Ud8oONpJD0Q-uJ4UQAYBgr_xHsv_LBNw_xt4MhA="],
)

# Per-provider webhook secrets for HMAC verification.
PAYMENT_WEBHOOK_SECRETS = {
    "FLYWIRE": env.str("FLYWIRE_WEBHOOK_SECRET", default="dev-flywire-secret"),
    "STRIPE": env.str("STRIPE_WEBHOOK_SECRET", default="dev-stripe-secret"),
}

# Public-facing SPA origin used to build user-clickable URLs in transactional
# email (password reset, magic link, account setup). Must include the scheme
# and no trailing slash.
FRONTEND_URL = env.str("FRONTEND_URL", default="http://localhost:5173")
PASSWORD_RESET_TTL_SECONDS = env.int("PASSWORD_RESET_TTL_SECONDS", default=3600)

# Ops mailbox(es) to BCC/notify on operational events (failed payments,
# escalations). Empty by default — handlers must skip the ops email when
# the list is empty instead of crashing.
OPS_EMAIL_RECIPIENTS = env.list("OPS_EMAIL_RECIPIENTS", default=[])

# Guardrail for the `seed_dev` management command. False here (and therefore
# in production, which inherits base) hard-blocks fake-data generation. Dev,
# test, and staging settings flip this to True. Never set in production.
SEED_DEV_ALLOWED = False

# Email safety: two independent default-closed gates protect real sends. Any
# settings module that fails to override these gets zero real email — see
# `production.py` / `staging.py` for the only places they flip open, and
# `comms/tasks._send` for the dispatch-layer assertion that mirrors the flag.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EMAIL_REAL_SENDS_ALLOWED = False
# Optional recipient allowlist (used on staging). Empty → no restriction.
# Entries are either an exact email or a `@domain.tld` suffix; matching is
# case-insensitive. See `comms.recipient_allowlist.filter_recipients`.
EMAIL_RECIPIENT_ALLOWLIST: list[str] = []

OPEN_AI_API_KEY = env.str("OPEN_AI_API_KEY", default="")
