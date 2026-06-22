"""Tests for the company-name → Organisation dedup helper (GAP-046)."""

from __future__ import annotations

import pytest

from accounts.enums import OrgType
from accounts.models import Organisation
from accounts.services.organisations import organisation_for_company_name


@pytest.mark.django_db
def test_blank_returns_none_and_creates_nothing() -> None:
    assert organisation_for_company_name(None) is None
    assert organisation_for_company_name("") is None
    assert organisation_for_company_name("   ") is None
    assert Organisation.objects.count() == 0


@pytest.mark.django_db
def test_creates_agency_with_content_hash_dedup_key() -> None:
    org = organisation_for_company_name("Dune Travel")

    assert org is not None
    assert org.name == "Dune Travel"
    assert org.org_type == OrgType.AGENCY
    assert org.dedup_key is not None and org.dedup_key.startswith("org-")
    # The synthesised hash is never written to legacy_id (CLAUDE.md).
    assert org.legacy_id is None


@pytest.mark.django_db
def test_case_and_whitespace_variants_converge_on_one_row() -> None:
    first = organisation_for_company_name("Dune Travel")
    again = organisation_for_company_name("  dune   TRAVEL ")

    assert first is not None and again is not None
    assert first.pk == again.pk
    assert Organisation.objects.count() == 1
    # Display name keeps the first-seen original casing.
    assert Organisation.objects.get().name == "Dune Travel"


@pytest.mark.django_db
def test_distinct_names_get_distinct_orgs() -> None:
    a = organisation_for_company_name("Dune Travel")
    b = organisation_for_company_name("Sandpiper Holidays")

    assert a is not None and b is not None
    assert a.pk != b.pk
    assert Organisation.objects.count() == 2


@pytest.mark.django_db
def test_idempotent_no_duplicate_on_rerun() -> None:
    organisation_for_company_name("Dune Travel")
    organisation_for_company_name("Dune Travel")

    assert Organisation.objects.count() == 1
