"""Boot contract for the staging settings module.

The Render worker/beat services crashed at boot because `production.py`
requires the ALLOWED_HOSTS env var and render.yaml only set it on the web
service. Staging defaults it instead — these tests pin that contract by
importing the module fresh under a controlled environment.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from types import ModuleType

import pytest

SETTINGS_MODULES = [
    "villacollective.settings.staging",
    "villacollective.settings.production",
]


@pytest.fixture
def import_staging(monkeypatch: pytest.MonkeyPatch) -> Callable[[], ModuleType]:
    """Import villacollective.settings.staging fresh and return the module."""

    def _import() -> ModuleType:
        for name in SETTINGS_MODULES:
            sys.modules.pop(name, None)
        try:
            return importlib.import_module("villacollective.settings.staging")
        finally:
            # Never leave a half-imported staging/production module cached for
            # other tests, and drop the env default the import may have set.
            for name in SETTINGS_MODULES:
                sys.modules.pop(name, None)
            monkeypatch.delenv("ALLOWED_HOSTS", raising=False)

    # Render provides all of these on every service; only ALLOWED_HOSTS is
    # under test.
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-secret")
    monkeypatch.setenv("EMAIL_RECIPIENT_ALLOWLIST", "ops@example.com")
    monkeypatch.setenv("FERNET_KEYS", "wIZ6Ud8oONpJD0Q-uJ4UQAYBgr_xHsv_LBNw_xt4MhA=")
    monkeypatch.setenv("FLYWIRE_WEBHOOK_SECRET", "test-flywire-secret")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "test-stripe-secret")
    # GAP-094: no default — a deploy that forgets the private documents bucket
    # must fail at boot rather than silently deny every guest their contract.
    monkeypatch.setenv("DOCUMENTS_S3_BUCKET", "test-documents-bucket")
    return _import


def test_staging_boots_without_allowed_hosts_env(
    import_staging: Callable[[], ModuleType], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    staging = import_staging()
    assert staging.ALLOWED_HOSTS == [".onrender.com"]


def test_staging_runs_celery_tasks_eagerly(
    import_staging: Callable[[], ModuleType],
) -> None:
    """Staging has no worker/beat services (cost) — tasks must run inline."""
    staging = import_staging()
    assert staging.CELERY_TASK_ALWAYS_EAGER is True
    assert staging.CELERY_TASK_EAGER_PROPAGATES is True


def test_explicit_allowed_hosts_env_still_wins(
    import_staging: Callable[[], ModuleType], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALLOWED_HOSTS", "demo.villacollective.com")
    staging = import_staging()
    assert staging.ALLOWED_HOSTS == ["demo.villacollective.com"]


def test_staging_and_production_use_separate_image_buckets(
    import_staging: Callable[[], ModuleType], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Separate buckets, not prefixes in one bucket: a staging reset
    # (`aws s3 rm --recursive …/staging/`) or a staging key must never be able
    # to touch production imagery. The `from .production import *` means
    # staging inherits the prod bucket unless it overrides it — pin both.
    staging = import_staging()
    assert staging.S3_STORAGE_OPTIONS["bucket_name"] == "villacollective-images"
    assert staging.S3_STORAGE_OPTIONS["location"] == "staging"

    # Production (unlike staging) has no ALLOWED_HOSTS default.
    monkeypatch.setenv("ALLOWED_HOSTS", "app.example.com")
    production = importlib.import_module("villacollective.settings.production")
    try:
        assert production.S3_STORAGE_OPTIONS["bucket_name"] == "villacollective-images-prod"
        assert production.S3_STORAGE_OPTIONS["location"] == "production"
    finally:
        for name in SETTINGS_MODULES:
            sys.modules.pop(name, None)
