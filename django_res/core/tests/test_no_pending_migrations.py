"""Guard: model state and migrations must never drift (SMELL-022).

The rate-grid / booking EXCLUDE constraints used to live only in raw
migration SQL, invisible to the autodetector. Now that models own every
constraint, this test makes the invariant durable: any model edit without a
matching migration fails the suite (`makemigrations --check` exits 1 on
drift, which surfaces here as SystemExit).
"""

import pytest
from django.core.management import call_command


@pytest.mark.django_db  # makemigrations probes the DB for migration-history consistency
def test_no_pending_migrations() -> None:
    # Default verbosity: on drift the captured stdout names the drifted
    # app/model instead of a bare `SystemExit: 1`.
    call_command("makemigrations", "--check", "--dry-run")
