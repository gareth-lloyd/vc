"""GAP-089: `import_enquiry_sheet` — Person (+ DEAD historic Enquiry per dated row)."""

from __future__ import annotations

import re
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.utils import timezone
from openpyxl import Workbook

from accounts.models import Organisation, Person, PersonEmail
from accounts.services.organisations import organisation_for_company_name
from properties.models import Country, Property, Region
from reservations.enums import EnquirySource, EnquiryStatus, LeadStatus
from reservations.models import Enquiry

pytestmark = pytest.mark.django_db

HEADER = [
    "Email sent",
    "Tags",
    "Linked",
    "Trade",
    "System Client Notes",
    "Task notes",
    "Prf",
    "First Name",
    "Last Name",
    "Email",
    "Phone",
    "Villa Enquired",
    "Country",
    "Region",
    "Enquiry Date",
    "Budget",
    "Source",
    "Villa(s) Booked",
    "Total Gross (€)",
    "Booking Count",
    "Notes",
]


def _row(**cells: Any) -> list[Any]:
    base: dict[str, Any] = {
        "First Name": "Ada",
        "Last Name": "Lovelace",
        "Email": "ada@example.com",
        "Source": "Email_B",
        "Budget": "None-None",
    }
    base.update(cells)
    return [base.get(col) for col in HEADER]


def _workbook(path: Path, rows: list[list[Any]]) -> Path:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Sheet1"
    ws.append(HEADER)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _run(path: Path, *args: str) -> str:
    out = StringIO()
    call_command("import_enquiry_sheet", "--file", str(path), *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def corfu(db: None) -> Region:
    country, _ = Country.objects.get_or_create(
        iso2="GR", defaults={"name": "Greece", "iso3": "GRC"}
    )
    return Region.objects.create(country=country, name="Corfu", slug="corfu")


@pytest.fixture
def villa(corfu: Region) -> Property:
    return Property.objects.create(
        name="Villa Yeraki", display_name="Villa Yeraki", slug="villa-yeraki", region=corfu
    )


def test_dated_row_creates_person_and_backstamped_dead_enquiry(
    tmp_path: Path, villa: Property, corfu: Region
) -> None:
    path = _workbook(
        tmp_path / "e.xlsx",
        [
            _row(
                **{
                    "Tags": "VIP; NC, LC",
                    "Trade": "Acme Travel",
                    "Phone": "+44 7985 414214",
                    "Villa Enquired": "Yeraki",
                    "Country": "Greece",
                    "Region": "Corfu",
                    "Enquiry Date": "2019-06-01",
                    "Budget": "£5,000 -£10,000",
                    "Notes": "Hello<br />Second line",
                    "Linked": "Charles Babbage",
                }
            )
        ],
    )

    out = _run(path)

    person = Person.objects.get(last_name="Lovelace")
    assert person.tags == ["nicks_friend", "vip"]
    assert person.agency is not None and person.agency.name == "Acme Travel"
    assert list(person.phones.values_list("number", flat=True)) == ["+447985414214"]
    assert person.notes == "Sheet tags: LC\nLinked to: Charles Babbage"
    enquiry = Enquiry.objects.get()
    assert enquiry.person == person
    assert enquiry.legacy_id is not None and enquiry.legacy_id.startswith("sheet-enquiry-")
    assert enquiry.reference.startswith("E-SHEET-")
    assert enquiry.status == EnquiryStatus.DEAD
    assert enquiry.lost_reason == "unknown"
    assert enquiry.lead_status == LeadStatus.COLD
    assert enquiry.site_source == EnquirySource.EMAIL_INBOUND
    assert enquiry.property == villa
    assert enquiry.region == corfu
    assert enquiry.email == "ada@example.com"
    assert enquiry.phone == "+447985414214"
    assert enquiry.inbound_message == (
        "Villa enquired: Yeraki\nSource: Email_B\nBudget: £5,000 -£10,000\n"
        "Destination: Corfu / Greece\n\nHello\nSecond line"
    )
    assert timezone.localtime(enquiry.created_at).date() == date(2019, 6, 1)
    assert "enquiry" in out


def test_undated_row_is_person_only_with_a_provenance_note(tmp_path: Path) -> None:
    path = _workbook(
        tmp_path / "e.xlsx",
        [_row(**{"Source": "VC Contacts Export", "Villa Enquired": "Yeraki", "Notes": "x<br>y"})],
    )

    out = _run(path)

    person = Person.objects.get(last_name="Lovelace")
    assert Enquiry.objects.count() == 0
    assert person.notes == (
        "Enquiry sheet (undated, source: VC Contacts Export); villa: Yeraki; notes: x / y"
    )
    assert "undated_row_person_only" in out


def test_res_enquiry_with_same_email_is_left_alone_and_sheet_row_still_lands(
    tmp_path: Path,
) -> None:
    # No cross-source dedupe: the res loader and the sheet cover different years.
    person = Person.objects.create(first_name="Ada", last_name="Lovelace", kind="customer")
    PersonEmail.objects.create(contact=person, email="ada@example.com", is_primary=True)
    res = Enquiry.objects.create(
        person=person, first_name="Ada", email="ada@example.com", legacy_id="enquiry-1"
    )
    path = _workbook(tmp_path / "e.xlsx", [_row(**{"Enquiry Date": "2019-06-01"})])

    _run(path)

    res.refresh_from_db()
    assert res.status == EnquiryStatus.NEW
    assert Enquiry.objects.count() == 2
    assert Person.objects.count() == 1
    assert Enquiry.objects.get(legacy_id__startswith="sheet-").person == person


def test_rerun_creates_nothing_and_keeps_a_reopened_enquiry(tmp_path: Path) -> None:
    path = _workbook(
        tmp_path / "e.xlsx",
        [_row(**{"Enquiry Date": "2019-06-01", "Tags": "VIP", "Phone": "+44 7985 414214"})],
    )
    _run(path)
    enquiry = Enquiry.objects.get()
    Enquiry.objects.filter(pk=enquiry.pk).update(status=EnquiryStatus.PROGRESSING, lost_reason="")

    out = _run(path)

    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.PROGRESSING
    assert Enquiry.objects.count() == 1
    assert Person.objects.count() == 1
    assert Person.objects.get().phones.count() == 1
    assert "exists" in out


def test_invalid_email_is_an_error_and_other_rows_continue(tmp_path: Path) -> None:
    path = _workbook(
        tmp_path / "e.xlsx",
        [
            _row(**{"Email": "not-an-email", "Enquiry Date": "2019-06-01"}),
            _row(**{"First Name": "Grace", "Last Name": "Hopper", "Email": "g@example.com"}),
        ],
    )

    out = _run(path)

    assert Person.objects.count() == 1
    assert Person.objects.get().last_name == "Hopper"
    assert re.search(r"Sheet1!2\s+invalid email", out)  # keyed by sheet row (BUG-030 §34)


def test_unknown_source_and_ambiguous_region_and_unmatched_villa(tmp_path: Path) -> None:
    gr, _ = Country.objects.get_or_create(iso2="GR", defaults={"name": "Greece", "iso3": "GRC"})
    Region.objects.create(country=gr, name="Corfu", slug="corfu-a")
    Region.objects.create(country=gr, name="Corfu", slug="corfu-b")
    path = _workbook(
        tmp_path / "e.xlsx",
        [
            _row(
                **{
                    "Source": "Trello",
                    "Villa Enquired": "Nowhere / Elsewhere",
                    "Country": "Greece",
                    "Region": "Corfu",
                    "Enquiry Date": "2020-02-02",
                }
            )
        ],
    )

    out = _run(path)

    enquiry = Enquiry.objects.get()
    assert enquiry.site_source == EnquirySource.OTHER
    assert enquiry.region is None
    assert enquiry.property is None
    assert "Nowhere / Elsewhere" in out


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    path = _workbook(tmp_path / "e.xlsx", [_row(**{"Enquiry Date": "2019-06-01"})])

    out = _run(path, "--dry-run")

    assert "[dry-run]" in out
    assert Person.objects.count() == 0
    assert Enquiry.objects.count() == 0


def test_sheet_minted_agencies_are_stamped_but_existing_ones_are_not(tmp_path: Path) -> None:
    legacy = organisation_for_company_name("Old Travel")  # as the legacy loader would
    path = _workbook(
        tmp_path / "e.xlsx",
        [
            _row(**{"Trade": "old travel"}),
            _row(
                **{
                    "First Name": "Grace",
                    "Last Name": "Hopper",
                    "Email": "g@example.com",
                    "Trade": "New Travel",
                }
            ),
        ],
    )

    _run(path)

    assert legacy is not None
    legacy.refresh_from_db()
    assert legacy.legacy_id is None
    assert Person.objects.get(last_name="Lovelace").agency == legacy
    minted = Organisation.objects.get(name="New Travel")
    assert minted.legacy_id is not None and minted.legacy_id.startswith("sheet-org-")
    assert Person.objects.get(first_name="Grace").agency == minted


def test_phone_is_not_added_to_a_legacy_owner_or_agent_person(tmp_path: Path) -> None:
    # A bare-legacy-id Person is a VillaContact row: `reconcile_legacy` compares
    # its channels against VillaContactTele, so the sheet must not add one.
    owner = Person.objects.create(
        first_name="Ada", last_name="Lovelace", kind="contact", legacy_id="42"
    )
    PersonEmail.objects.create(contact=owner, email="ada@example.com", is_primary=True)
    path = _workbook(tmp_path / "e.xlsx", [_row(**{"Phone": "+44 7985 414214"})])

    _run(path)

    assert Person.objects.count() == 1
    assert owner.phones.count() == 0


def test_a_row_that_fails_after_its_person_is_counted_counts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BUG-030 §34: the row's savepoint rolls the person back, so the report
    must not keep the `created person` it counted before the failure."""
    from data_migration.management.commands import import_enquiry_sheet

    def _boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("enquiry write failed")

    monkeypatch.setattr(import_enquiry_sheet.Command, "_import_enquiry", _boom)
    path = _workbook(tmp_path / "e.xlsx", [_row(**{"Enquiry Date": "2019-06-01"})])

    out = _run(path)

    assert Person.objects.count() == 0
    assert "enquiry write failed" in out
    assert not re.search(r"created\s+person", out)
