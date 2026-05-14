from __future__ import annotations

import pytest

from comms.enums import SmtpScope
from comms.models import SmtpProfile


@pytest.fixture
def system_profile(db: None) -> SmtpProfile:
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
