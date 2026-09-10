"""Shared legacy-parse helpers (GAP-006 remediation) + person_for_client."""

from __future__ import annotations

from datetime import datetime

import pytest

from data_migration.loaders._util import (
    legacy_changed_since_sql,
    legacy_deleted_sql,
    legacy_quotation_no,
    legacy_row_deleted,
    person_for_client,
)


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"DeletedAt": None, "DeletedBy": None}, False),
        ({"DeletedAt": None, "DeletedBy": ""}, False),
        ({"DeletedAt": None, "DeletedBy": "   "}, False),
        ({"DeletedAt": "2024-01-01", "DeletedBy": None}, True),
        ({"DeletedAt": None, "DeletedBy": "admin"}, True),
        ({}, False),
    ],
)
def test_legacy_row_deleted(row: dict[str, object], expected: bool) -> None:
    # GAP-107: a legacy row is deleted iff EITHER convention says so —
    # `DeletedAt IS NOT NULL` (Django loaders) or `ISNULL(DeletedBy,'') <> ''`
    # (legacy's own views).
    assert legacy_row_deleted(row) is expected


def test_legacy_deleted_sql_is_the_or_predicate() -> None:
    assert legacy_deleted_sql() == "(DeletedAt IS NOT NULL OR ISNULL(DeletedBy, '') <> '')"
    assert legacy_deleted_sql("r.") == "(r.DeletedAt IS NOT NULL OR ISNULL(r.DeletedBy, '') <> '')"


def test_legacy_changed_since_sql_covers_insert_update_and_delete_stamps() -> None:
    # Legacy `sp_regions` / `sp_countries` stamp a different column per
    # action; a delta load must see all three.
    clause = legacy_changed_since_sql(datetime(2026, 1, 2, 3, 4, 5))
    assert clause == (
        "(UpdateAt > '2026-01-02T03:04:05' OR DeletedAt > '2026-01-02T03:04:05' "
        "OR CreatedAt > '2026-01-02T03:04:05')"
    )


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
