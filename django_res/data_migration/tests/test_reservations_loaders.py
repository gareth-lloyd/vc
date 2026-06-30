"""ClientLoader / EnquiryLoader behaviour (GAP-045 D5-3 honest-integrity import).

ClientLoader writes `accounts.Person` directly (no Guest), keyed `client-{Id}`,
reconciling the single legacy email/phone onto a PRIMARY child IN PLACE. The
transform tests stay pure dict-transform; the run-twice idempotency test
exercises the Postgres schema (`@pytest.mark.django_db`) — a pure transform test
can't catch the duplicate-primary constraint trip a re-run would otherwise cause.
"""

from __future__ import annotations

import pytest

from accounts.enums import ContactRole, PersonKind, PersonStatus
from accounts.models import Person
from data_migration.base import LoadReport
from data_migration.loaders.reservations import ClientLoader, EnquiryLoader, _role_for


@pytest.mark.parametrize(
    "role_id,expected",
    [
        (1, ContactRole.OWNER),
        (2, ContactRole.AGENT),
        (3, ContactRole.VILLA_ADMIN),
        (4, ContactRole.MANAGER),
        (5, ContactRole.MANAGEMENT_COMPANY),
    ],
)
def test_role_for_maps_verified_legacy_villaroles(role_id: int, expected: str) -> None:
    """Legacy VillaRoles ids (1=Owner 2=Agent 3=Villa Admin 4=Villa Manager
    5=Management Company; see 07-api-schema-reconciliation.md) map 1:1."""
    assert _role_for(role_id) == expected


def test_role_for_unmapped_or_null_defaults_to_owner() -> None:
    # Legacy had exactly ids 1-5; a NULL/absent role mapping falls back to owner.
    assert _role_for(None) == ContactRole.OWNER
    assert _role_for(0) == ContactRole.OWNER
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
