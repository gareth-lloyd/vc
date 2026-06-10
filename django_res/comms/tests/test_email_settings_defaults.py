"""Pin cast-iron email defaults against a future "tidy-up" of base settings.

These tests load each environment's settings module in-process and assert
the two gates are configured as the design demands. They are the safety
net against a regression that "just tidies up base.py" by removing the
locmem default or flipping `EMAIL_REAL_SENDS_ALLOWED`.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType

import pytest
from django.conf import settings

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
SMTP = "django.core.mail.backends.smtp.EmailBackend"


def _fresh_import(module: str) -> ModuleType:
    sys.modules.pop(module, None)
    return importlib.import_module(module)


def test_base_settings_default_closed() -> None:
    base = _fresh_import("villacollective.settings.base")
    assert base.EMAIL_BACKEND == LOCMEM
    assert base.EMAIL_REAL_SENDS_ALLOWED is False
    assert base.EMAIL_RECIPIENT_ALLOWLIST == []


def test_dev_inherits_closed_defaults() -> None:
    # Reload base first so dev's `from .base import *` picks up a clean state.
    _fresh_import("villacollective.settings.base")
    dev = _fresh_import("villacollective.settings.dev")
    assert dev.EMAIL_BACKEND == LOCMEM
    assert dev.EMAIL_REAL_SENDS_ALLOWED is False


def test_active_test_settings_use_locmem() -> None:
    """Pytest itself must run under the locmem backend with the gate open.

    Asserts against `django.conf.settings` (the live config used by every
    other test in the suite) rather than re-importing the module — this is
    the load-bearing safety net: if base ever flips to SMTP and `test.py`
    forgets to override, this test fails before any real socket can open.
    """
    assert settings.EMAIL_BACKEND == LOCMEM
    assert settings.EMAIL_REAL_SENDS_ALLOWED is True


def test_production_opens_both_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    # Production settings demand these env vars at import time.
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-prod-key")
    monkeypatch.setenv("ALLOWED_HOSTS", "example.com")
    monkeypatch.setenv("FERNET_KEYS", "wIZ6Ud8oONpJD0Q-uJ4UQAYBgr_xHsv_LBNw_xt4MhA=")
    monkeypatch.setenv("FLYWIRE_WEBHOOK_SECRET", "test-flywire-secret")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "test-stripe-secret")
    _fresh_import("villacollective.settings.base")
    prod = _fresh_import("villacollective.settings.production")
    assert prod.EMAIL_BACKEND == SMTP
    assert prod.EMAIL_REAL_SENDS_ALLOWED is True
    # No restriction by default; ops set it via env if they want one.
    assert prod.EMAIL_RECIPIENT_ALLOWLIST == []
