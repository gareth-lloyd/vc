"""Shared legacy-parse helpers (GAP-006 remediation) + person_for_client."""

from __future__ import annotations

import pytest

from data_migration.loaders._util import legacy_quotation_no, person_for_client


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1805, 1805),
        ("1805", 1805),
        (0, None),
        ("0", None),
        (-3, None),
        (None, None),
        ("not-a-number", None),
    ],
)
def test_legacy_quotation_no(raw: object, expected: int | None) -> None:
    assert legacy_quotation_no({"QuotationNo": raw}) == expected


def test_legacy_quotation_no_missing_key() -> None:
    assert legacy_quotation_no({}) is None


def test_person_for_client_returns_none_for_no_id() -> None:
    # No client reference → None (the caller early-returns, mirroring the prior
    # `guest is None` skip). No DB access on this path.
    assert person_for_client(None) is None
    assert person_for_client("") is None
    assert person_for_client(0) is None


@pytest.mark.django_db
def test_person_for_client_resolves_existing_client_person(db: None) -> None:
    from accounts.enums import PersonKind
    from accounts.models import Person

    person = Person.objects.create(
        first_name="Ada", last_name="Lovelace", legacy_id="client-55", kind=PersonKind.CUSTOMER
    )
    assert person_for_client(55) == person
    # Accepts a str id too (downstream rows pass the raw legacy column value).
    assert person_for_client("55") == person


@pytest.mark.django_db
def test_person_for_client_falls_back_to_unknown_client_sentinel(db: None) -> None:
    """A client ClientLoader skipped (the no-name row) has no `client-{id}`
    Person; rather than a `DoesNotExist`/silent drop, we fall back to the stable
    `unknown_client` sentinel (idempotent), so the downstream row is preserved."""
    from data_migration.loaders.sentinels import UNKNOWN_CLIENT_LEGACY_ID, unknown_client

    resolved = person_for_client(999)
    assert resolved.legacy_id == UNKNOWN_CLIENT_LEGACY_ID
    # Idempotent: a second unresolvable lookup returns the same sentinel row.
    assert person_for_client(998) == resolved == unknown_client()
