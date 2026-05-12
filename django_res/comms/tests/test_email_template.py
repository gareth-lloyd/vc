from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from comms.models import EmailTemplate


@pytest.mark.django_db
def test_unique_active_template_per_key() -> None:
    EmailTemplate.objects.create(
        key="booking.confirmation",
        version=1,
        subject_template="Confirmed",
        body_template="Hi",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        EmailTemplate.objects.create(
            key="booking.confirmation",
            version=2,
            subject_template="Confirmed v2",
            body_template="Hi v2",
        )


@pytest.mark.django_db
def test_inactive_versions_coexist() -> None:
    EmailTemplate.objects.create(
        key="booking.confirmation",
        version=1,
        subject_template="v1",
        body_template="v1",
        is_active=False,
    )
    # New active row is allowed because no other row for this key is active.
    EmailTemplate.objects.create(
        key="booking.confirmation",
        version=2,
        subject_template="v2",
        body_template="v2",
        is_active=True,
    )


@pytest.mark.django_db
def test_unique_key_version_pair() -> None:
    EmailTemplate.objects.create(
        key="booking.confirmation",
        version=1,
        subject_template="v1",
        body_template="v1",
        is_active=False,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        EmailTemplate.objects.create(
            key="booking.confirmation",
            version=1,
            subject_template="dup",
            body_template="dup",
            is_active=False,
        )
