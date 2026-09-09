"""Local development settings."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from core.logging.config import configure_structlog

from .base import *  # noqa: F403
from .base import LOG_LEVEL

# WeasyPrint's cffi loader can't find Homebrew's gobject/pango on macOS unless
# the fallback library path points at the brew prefix (GAP-094). Only a hint —
# an explicit env var wins, and non-darwin hosts are untouched. Setting the
# var *replaces* the default search list `ctypes.macholib.dyld` would use, so
# spell out that list too, or a host with its libraries under /usr/local/lib
# (Intel brew, MacPorts) would stop finding them in-process.
if sys.platform == "darwin":
    _brew_lib = Path(os.environ.get("HOMEBREW_PREFIX", "/opt/homebrew")) / "lib"
    if _brew_lib.is_dir():
        os.environ.setdefault(
            "DYLD_FALLBACK_LIBRARY_PATH",
            f"{_brew_lib}:{Path.home() / 'lib'}:/usr/local/lib:/lib:/usr/lib",
        )

DEBUG = True
ALLOWED_HOSTS = ["*"]

ENVIRONMENT = "dev"
# Human-readable coloured console logs locally instead of JSON.
LOG_JSON = False
LOGGING = configure_structlog(json_logs=False, level=LOG_LEVEL)
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# Local dev may seed fake data (see core/management/commands/seed_dev.py).
SEED_DEV_ALLOWED = True

# Skip the TOTP challenge at login locally: the pre-enrolled `glloyd` dev
# superuser and Playwright log in with just a password. Fail-closed default
# (True) lives in base.py; this is the only module that opens it.
TFA_LOGIN_CHALLENGE = False

# Email safety: dev intentionally inherits both gates from base
# (EMAIL_BACKEND=locmem, EMAIL_REAL_SENDS_ALLOWED=False). Do not override.
# To inspect outgoing mail, read `EmailLog` rows or `django.core.mail.outbox`.
