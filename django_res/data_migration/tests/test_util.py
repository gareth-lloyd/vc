"""Shared legacy-parse helpers (GAP-006 remediation) + person_for_client."""

from __future__ import annotations

import pytest

from data_migration.loaders._util import (
    LEGACY_COUNTRY_ALIASES,
    LEGACY_REGION_REMAP,
    country_for_legacy_id,
    legacy_deleted_sql,
    legacy_quotation_no,
    legacy_row_deleted,
    person_for_client,
    region_for_legacy_id,
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


# --- BUG-030 §8 region remap ---


def test_region_remap_table_is_the_ticket_decision() -> None:
    assert LEGACY_REGION_REMAP == {"25": "61", "27": "60"}


@pytest.mark.django_db
def test_region_for_legacy_id_returns_the_row_when_not_remapped() -> None:
    from properties.models.geo import Country, Region

    country = Country.objects.get(iso2="GR")
    region = Region.objects.create(country=country, name="Crete", slug="crete", legacy_id="55")
    assert region_for_legacy_id("55") == region
    assert region_for_legacy_id("999") is None
    assert region_for_legacy_id("") is None


@pytest.mark.django_db
def test_region_for_legacy_id_follows_the_remap() -> None:
    from properties.models.geo import Country, Region

    country = Country.objects.get(iso2="GR")
    twin = Region.objects.create(country=country, name="Twin", slug="twin", legacy_id="61")
    Region.objects.create(country=country, name="Dup", slug="dup", legacy_id="25")
    assert region_for_legacy_id("25") == twin


# --- BUG-030 §6 England alias ---


def test_country_alias_table_is_the_england_row() -> None:
    assert LEGACY_COUNTRY_ALIASES == {"24": "GB"}


@pytest.mark.django_db
def test_country_for_legacy_id_returns_the_stamped_row() -> None:
    from properties.models.geo import Country

    fr = Country.objects.get(iso2="FR")
    fr.legacy_id = "42"
    fr.save(update_fields=["legacy_id"])
    assert country_for_legacy_id("42") == fr
    assert country_for_legacy_id("999") is None
    assert country_for_legacy_id("") is None


@pytest.mark.django_db
def test_country_for_legacy_id_aliases_england_to_gb() -> None:
    import structlog

    from properties.models.geo import Country

    gb = Country.objects.get(iso2="GB")
    assert gb.legacy_id != "24"
    with structlog.testing.capture_logs() as logs:
        assert country_for_legacy_id("24") == gb
    assert any(
        log["event"] == "data_migration.country_aliased"
        and log["legacy_country_id"] == "24"
        and log["aliased_to"] == "GB"
        for log in logs
    )
