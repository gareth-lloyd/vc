"""ContactLoader agency rerouting + the dedupe_organisations reporter (GAP-046)."""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.db import IntegrityError

from accounts.enums import OrgType
from accounts.factories import OrganisationFactory
from accounts.models import Organisation, Person
from data_migration.base import LoadReport
from data_migration.loaders.people import ContactLoader


def _row(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "Id": 1,
        "Title": "",
        "FirstName": "Grace",
        "LastName": "Hopper",
        "Company": "Dune Travel",
        "WebsiteUrl": "",
        "Notes": "",
        "PrefferedMethod": 1,
        "AddressLine1": "",
        "AddressLine2": "",
        "DeletedAt": None,
    }
    base.update(over)
    return base


@pytest.mark.django_db
def test_loader_creates_and_links_agency() -> None:
    ContactLoader()._process_row(_row(), LoadReport(loader="contact"))

    person = Person.objects.get(legacy_id="1")
    assert person.agency is not None
    assert person.agency.name == "Dune Travel"
    assert person.agency.org_type == OrgType.AGENCY
    assert Organisation.objects.count() == 1


@pytest.mark.django_db
def test_loader_idempotent_no_duplicate_org() -> None:
    ContactLoader()._process_row(_row(Id=1), LoadReport(loader="contact"))
    ContactLoader()._process_row(_row(Id=2, Company="dune travel"), LoadReport(loader="contact"))

    assert Organisation.objects.count() == 1
    assert (
        Person.objects.get(legacy_id="1").agency_id == Person.objects.get(legacy_id="2").agency_id
    )


@pytest.mark.django_db
def test_loader_blank_company_leaves_null_agency() -> None:
    ContactLoader()._process_row(_row(Company=""), LoadReport(loader="contact"))

    assert Person.objects.get(legacy_id="1").agency_id is None
    assert Organisation.objects.count() == 0


@pytest.mark.django_db
def test_failed_person_write_leaves_no_orphan_org(monkeypatch: pytest.MonkeyPatch) -> None:
    """R1: the org get_or_create runs inside the same per-row savepoint as the
    Person write, so a write-time failure rolls the org back too — no orphan."""

    def boom(*args: Any, **kwargs: Any) -> None:
        raise IntegrityError("simulated person write failure")

    monkeypatch.setattr(Person._default_manager, "update_or_create", boom)

    report = LoadReport(loader="contact")
    ContactLoader()._load_rows([_row()], report)

    assert report.errors  # the row was recorded as failed
    assert not Organisation.objects.filter(name="Dune Travel").exists()


@pytest.mark.django_db
def test_dedupe_reports_near_duplicates_and_writes_nothing() -> None:
    OrganisationFactory(name="Dune Travel")
    OrganisationFactory(name="Dune Travel Ltd")
    OrganisationFactory(name="Sandpiper Holidays")
    before = Organisation.objects.count()

    out = StringIO()
    call_command("dedupe_organisations", "--threshold", "0.8", stdout=out)
    output = out.getvalue()

    assert "Dune Travel" in output
    assert "Dune Travel Ltd" in output
    assert "Sandpiper Holidays" not in output
    assert "wrote nothing" in output
    # Read-only: no merge happened.
    assert Organisation.objects.count() == before


@pytest.mark.django_db
def test_dedupe_reports_clean_when_no_near_duplicates() -> None:
    OrganisationFactory(name="Alpha")
    OrganisationFactory(name="Zeta")

    out = StringIO()
    call_command("dedupe_organisations", stdout=out)

    assert "No near-duplicate organisations found." in out.getvalue()
