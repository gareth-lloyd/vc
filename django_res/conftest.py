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
