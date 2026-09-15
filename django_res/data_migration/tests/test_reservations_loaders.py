"""ClientLoader / EnquiryLoader behaviour (GAP-045 D5-3 honest-integrity import).

ClientLoader writes `accounts.Person` directly (no Guest), keyed `client-{Id}`,
reconciling the single legacy email/phone onto a PRIMARY child IN PLACE. The
transform tests stay pure dict-transform; the run-twice idempotency test
exercises the Postgres schema (`@pytest.mark.django_db`) — a pure transform test
can't catch the duplicate-primary constraint trip a re-run would otherwise cause.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from django.utils import timezone

from accounts.enums import ContactRole, PersonKind, PersonPreferredMethod, PersonStatus
from accounts.models import Person
from data_migration.base import LoadReport
from data_migration.loaders.reservations import ClientLoader, EnquiryLoader, _role_for
from reservations.models import Enquiry


@pytest.mark.parametrize(
    "role_id,expected",
    [
        # RoleId in the dump is the VillaRoles **Code** (10/20/40/50/80), not
        # the Id (1-5). Verified against the live 24-Apr dump.
        (10, ContactRole.OWNER),
        (20, ContactRole.AGENT),
        (40, ContactRole.VILLA_ADMIN),
        (50, ContactRole.MANAGER),
        (80, ContactRole.MANAGEMENT_COMPANY),
    ],
)
def test_role_for_maps_verified_legacy_villaroles(role_id: int, expected: str) -> None:
    """Legacy VillaRoles codes (10=Owner 20=Agent 40=Villa Admin 50=Villa
    Manager 80=Management Company; see 07-api-schema-reconciliation.md) map
    1:1. The role FKs in the dump store the Code, not the Id."""
    assert _role_for(role_id) == expected


def test_role_for_unmapped_or_null_defaults_to_owner() -> None:
    # A NULL/absent role mapping - and the old Id scale (1-5), which is NOT what
    # the dump stores - all fall back to owner.
    assert _role_for(None) == ContactRole.OWNER
    assert _role_for(0) == ContactRole.OWNER
    assert _role_for(1) == ContactRole.OWNER
    assert _role_for(99) == ContactRole.OWNER


def _client_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": 1,
        "FirstName": "Ada",
        "LastName": "Lovelace",
        "Email": "",
        "MobileNo": "",
    }
    base.update(overrides)
    return base


def test_client_phone_only_imports_with_null_email() -> None:
    """A phone-only legacy client is now a valid Person (was dropped before)."""
    kwargs = ClientLoader().transform(_client_row(MobileNo="+44 7911 123456"))
    assert kwargs is not None
    assert kwargs["_email"] is None
    assert kwargs["_phone"] == "+447911123456"
    assert kwargs["status"] == PersonStatus.ACTIVE.value
    assert kwargs["kind"] == PersonKind.CUSTOMER.value


def test_client_email_only_is_active_and_lowercased() -> None:
    kwargs = ClientLoader().transform(_client_row(Email="ADA@Example.com"))
    assert kwargs is not None
    assert kwargs["_email"] == "ada@example.com"
    assert kwargs["status"] == PersonStatus.ACTIVE.value


def test_client_channelless_is_dispositioned_inactive() -> None:
    """No email and no phone → INACTIVE (the Guest path's ARCHIVED equivalent)."""
    kwargs = ClientLoader().transform(_client_row(Email="", MobileNo=""))
    assert kwargs is not None
    assert kwargs["_email"] is None
    assert kwargs["_phone"] == ""
    assert kwargs["status"] == PersonStatus.INACTIVE.value


def test_client_email_without_at_becomes_null() -> None:
    kwargs = ClientLoader().transform(_client_row(Email="not-an-email", MobileNo="+44 7911 123456"))
    assert kwargs is not None
    assert kwargs["_email"] is None


def test_client_with_no_name_is_skipped() -> None:
    assert ClientLoader().transform(_client_row(FirstName="", LastName="")) is None


@pytest.mark.django_db
def test_client_loader_writes_person_keyed_client_with_primary_children(db: None) -> None:
    """The loader writes a `client-{Id}` Person plus PRIMARY email/phone children."""
    ClientLoader()._process_row(
        _client_row(Email="ada@example.com", MobileNo="+44 7911 123456"),
        LoadReport(loader="client"),
    )

    person = Person.objects.get(legacy_id="client-1")
    assert person.kind == PersonKind.CUSTOMER.value
    assert person.status == PersonStatus.ACTIVE.value
    assert person.emails.get(is_primary=True).email == "ada@example.com"
    assert person.phones.get(is_primary=True).number == "+447911123456"


@pytest.mark.django_db
def test_client_loader_rerun_with_changed_email_keeps_one_primary(db: None) -> None:
    """Run-twice idempotency (the BLOCKER guard): change a client's email, re-run.

    A blind `PersonEmail.objects.create(is_primary=True)` on the second run (or
    when the legacy email changed) would insert a SECOND primary and trip
    `one_primary_email_per_contact`; BaseLoader's per-row savepoint would then
    silently log it as an error. The shared in-place reconcile must instead
    UPDATE the single primary — exactly one primary email survives, no
    IntegrityError, no duplicate. A pure transform test can't reach this.
    """
    report = LoadReport(loader="client")
    ClientLoader()._process_row(
        _client_row(Email="ada@example.com", MobileNo="+44 7911 123456"), report
    )
    # The legacy email changed between dumps.
    ClientLoader()._process_row(
        _client_row(Email="ada.new@example.com", MobileNo="+44 7911 123456"), report
    )

    assert report.errors == []
    assert Person.objects.filter(legacy_id="client-1").count() == 1
    person = Person.objects.get(legacy_id="client-1")
    primaries = person.emails.filter(is_primary=True)
    assert primaries.count() == 1
    assert primaries.get().email == "ada.new@example.com"
    # The phone is unchanged and stays a single primary (no duplicate either).
    assert person.phones.filter(is_primary=True).count() == 1


def _enquiry_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": 1,
        "FirstName": "Ada",
        "LastName": "Lovelace",
        "Email": "",
        "CountryCode": "",
        "MobileNo": "",
        "Adult": 2,
        "Children": 0,
    }
    base.update(overrides)
    return base


def test_enquiry_phone_normalized_to_e164_via_calling_code() -> None:
    """The crude `+{cc} {number}` is replaced by E.164 normalization."""
    kwargs = EnquiryLoader().transform(_enquiry_row(CountryCode="44", MobileNo="07911 123456"))
    assert kwargs is not None
    assert kwargs["phone"] == "+447911123456"


def test_enquiry_empty_phone_stays_empty() -> None:
    kwargs = EnquiryLoader().transform(_enquiry_row())
    assert kwargs is not None
    assert kwargs["phone"] == ""


# --- GAP-089: created_at back-stamp (date coherence next to the sheet import) ---


def _enquiry_db_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        **_enquiry_row(),
        "Email": "ada@example.com",
        "Status": 0,
        "EnquiryNo": "E-000001",
        "CreatedAt": datetime(2024, 11, 20, 9, 15),
    }
    base.update(overrides)
    return base


def test_enquiry_created_at_backstamped_from_legacy(db: None) -> None:
    """Res enquiries must sort by their real date next to the 2017-2024 sheet
    rows (GAP-089), so `CreatedAt` is back-stamped past `auto_now_add`."""
    report = LoadReport(loader="enquiry")

    EnquiryLoader()._process_row(_enquiry_db_row(), report)

    enquiry = Enquiry.objects.get(legacy_id="1")
    assert timezone.is_aware(enquiry.created_at)
    assert enquiry.created_at == timezone.make_aware(datetime(2024, 11, 20, 9, 15))
    assert report.created == 1


def test_enquiry_created_at_backstamp_survives_rerun(db: None) -> None:
    report = LoadReport(loader="enquiry")
    row = _enquiry_db_row()
    EnquiryLoader()._process_row(row, report)
    EnquiryLoader()._process_row(row, report)

    enquiry = Enquiry.objects.get(legacy_id="1")
    assert enquiry.created_at == timezone.make_aware(datetime(2024, 11, 20, 9, 15))
    assert Enquiry.objects.count() == 1


def test_enquiry_without_legacy_created_at_keeps_auto_stamp(db: None) -> None:
    report = LoadReport(loader="enquiry")
    before = timezone.now()

    EnquiryLoader()._process_row(_enquiry_db_row(CreatedAt=None), report)

    assert Enquiry.objects.get(legacy_id="1").created_at >= before


# --- BUG-030 §8: the region remap applies to enquiries too ---


def test_enquiry_region_follows_the_legacy_region_remap(db: None) -> None:
    from properties.models.geo import Country, Region

    country = Country.objects.get(iso2="GR")
    twin = Region.objects.create(country=country, name="Twin", slug="twin", legacy_id="61")
    kwargs = EnquiryLoader().transform(_enquiry_row(RegionsId="25"))
    assert kwargs is not None
    assert kwargs["region"] == twin


# --- BUG-030 §6: the England alias applies to clients too ---


def test_client_under_legacy_england_attaches_to_gb(db: None) -> None:
    from properties.models.geo import Country

    kwargs = ClientLoader().transform(_client_row(CountryId=24))
    assert kwargs is not None
    assert kwargs["country"] == Country.objects.get(iso2="GB")


# --- BUG-030 §17/§19: client phone region, ContactType, CreatedAt ---


def test_client_query_selects_contact_type_and_created_at() -> None:
    assert "ContactType" in ClientLoader.legacy_query
    assert "CreatedAt" in ClientLoader.legacy_query


def test_client_bare_mobile_defaults_to_gb(db: None) -> None:
    kwargs = ClientLoader().transform(_client_row(MobileNo="07911123456"))
    assert kwargs is not None
    assert kwargs["_phone"] == "+447911123456"


def test_client_bare_mobile_is_anchored_on_its_country(db: None) -> None:
    from properties.models.geo import Country

    Country.objects.filter(iso2="GR").update(legacy_id="9")
    kwargs = ClientLoader().transform(_client_row(CountryId=9, MobileNo="6944123456"))
    assert kwargs is not None
    assert kwargs["_phone"] == "+306944123456"


@pytest.mark.parametrize(
    ("contact_type", "expected"),
    [
        ("Email", PersonPreferredMethod.EMAIL),
        ("Mobile", PersonPreferredMethod.PHONE),
        (" phone ", PersonPreferredMethod.PHONE),
        ("MOBILE", PersonPreferredMethod.PHONE),
        ("", PersonPreferredMethod.EMAIL),
        (None, PersonPreferredMethod.EMAIL),
        ("Fax", PersonPreferredMethod.EMAIL),
    ],
)
def test_client_contact_type_sets_preferred_method(
    contact_type: str | None, expected: PersonPreferredMethod
) -> None:
    kwargs = ClientLoader().transform(_client_row(ContactType=contact_type, Email="a@b.com"))
    assert kwargs is not None
    assert kwargs["preferred_method"] == expected


def test_client_created_at_is_backstamped_from_legacy(db: None) -> None:
    report = LoadReport(loader="client")
    ClientLoader()._process_row(
        _client_row(Email="ada@example.com", CreatedAt=datetime(2023, 4, 2, 10, 30)), report
    )
    person = Person.objects.get(legacy_id="client-1")
    assert person.created_at == timezone.make_aware(datetime(2023, 4, 2, 10, 30))


def test_client_without_legacy_created_at_keeps_auto_stamp(db: None) -> None:
    before = timezone.now()
    ClientLoader()._process_row(_client_row(Email="ada@example.com"), LoadReport(loader="client"))
    assert Person.objects.get(legacy_id="client-1").created_at >= before
