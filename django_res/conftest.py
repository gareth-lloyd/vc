"""Top-level pytest fixtures shared across apps.

App-scoped fixtures live in `<app>/tests/conftest.py`. Anything fanning
out across apps (e.g. a SYSTEM SmtpProfile that any cross-app email test
needs) belongs here so individual app conftests don't have to redeclare
it.
"""

from __future__ import annotations

import pytest

from comms.enums import SmtpScope
from comms.models import SmtpProfile


def _ensure_seeded_reference_data() -> None:
    """Top up data-migration-seeded reference rows that transactional tests wipe.

    The only `transaction=True` tests in the suite live in `seeding/tests/`;
    on teardown they flush every table — including rows created by data
    migrations (the ISO-3166 `Country` set from `properties.0009`, the on-disk
    `EmailTemplate` seeds from `comms.0003`-`0008`). Under `--reuse-db` those
    rows are never restored, so any later test — in this session or the next
    reused-DB run — that depends on them fails (`Country.DoesNotExist`, comms
    seed-sync no longer a no-op, …).

    Re-seed idempotently before each DB test. The guards make this a single
    cheap `EXISTS` query in the common case; the actual reseed only runs right
    after a seeding test has flushed the table, restoring the post-migration
    baseline every other test already assumes.
    """
    from properties.models import Country

    if not Country.objects.exists():
        from django_countries import countries as dc_countries

        Country.objects.bulk_create(
            [
                Country(
                    iso2=iso2,
                    name=str(name),
                    iso3=dc_countries.alpha3(iso2) or iso2 + "_",
                    sort_order=sort_order,
                    is_active=True,
                )
                for sort_order, (iso2, name) in enumerate(dc_countries)
            ],
            ignore_conflicts=True,
        )

    from comms.models import EmailTemplate

    if not EmailTemplate.objects.exists():
        from comms.management.commands.seed_email_templates import sync_templates

        sync_templates()


@pytest.fixture(autouse=True)
def _restore_seeded_reference_data(request: pytest.FixtureRequest) -> None:
    """Restore migration-seeded reference data for every DB-using test.

    Picks the DB fixture matching the test's mode so transactional tests get
    their flushed rows restored, while non-transactional tests reseed within
    their own rolled-back transaction. Tests with no `django_db` marker (pure
    unit tests) touch no DB and are skipped.
    """
    marker = request.node.get_closest_marker("django_db")
    if marker is None:
        return
    is_transactional = bool(marker.kwargs.get("transaction") or (marker.args and marker.args[0]))
    request.getfixturevalue("transactional_db" if is_transactional else "db")
    _ensure_seeded_reference_data()


@pytest.fixture
def run_on_commit_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run ``transaction.on_commit`` callbacks immediately instead of deferring.

    Email/webhook dispatch is enqueued via ``transaction.on_commit`` so the
    Celery worker never reads a row before its creating transaction commits.
    Under pytest-django each test runs in a rolled-back transaction that never
    commits, so those callbacks would otherwise never fire. Modules exercising
    a synchronous send-then-assert flow opt in with::

        pytestmark = pytest.mark.usefixtures("run_on_commit_immediately")

    Tests that specifically assert the *deferral* must NOT use this fixture;
    they use ``django_capture_on_commit_callbacks`` directly.
    """
    monkeypatch.setattr(
        "django.db.transaction.on_commit",
        lambda func, using=None, robust=False: func(),
    )


@pytest.fixture
def system_profile(db: None) -> SmtpProfile:
    """Default system SmtpProfile used by tests that fire transactional email."""
    return SmtpProfile.objects.create(
        name="System",
        scope=SmtpScope.SYSTEM,
        owner=None,
        host="smtp.example.com",
        port=587,
        username="system",
        encrypted_password="systempw",
        use_tls=True,
        from_email="noreply@example.com",
    )
