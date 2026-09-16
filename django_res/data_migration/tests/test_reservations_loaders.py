"""ClientLoader / EnquiryLoader behaviour (GAP-045 D5-3 honest-integrity import).

ClientLoader writes `accounts.Person` directly (no Guest), keyed `client-{Id}`,
reconciling the single legacy email/phone onto a PRIMARY child IN PLACE. The
transform tests stay pure dict-transform; the run-twice idempotency test
exercises the Postgres schema (`@pytest.mark.django_db`) — a pure transform test
can't catch the duplicate-primary constraint trip a re-run would otherwise cause.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from accounts.enums import ContactRole, PersonKind, PersonPreferredMethod, PersonStatus
from accounts.models import Person
from data_migration.base import LoadReport
from data_migration.loaders.reservations import ClientLoader, EnquiryLoader, _role_for
from reservations.enums import EnquiryLostReason, EnquirySource, EnquiryStatus, LeadStatus
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


# --- GAP-108 U8b: the nameless-client → enquiry-name fallback ---


def test_nameless_client_takes_the_name_off_its_enquiry(db: None) -> None:
    """From ~Nov-2025 ResProd writes VillaClientDetails with Email/CreatedBy only;
    the customer's name lives on the VillaEnquire behind the client's quotation."""
    kwargs = ClientLoader().transform(
        _client_row(
            FirstName="",
            LastName="",
            Email="ada@example.com",
            MobileNo="07911123456",
            EnquiryFirstName="Ada",
            EnquiryLastName="Lovelace",
        )
    )
    assert kwargs is not None
    assert (kwargs["first_name"], kwargs["last_name"]) == ("Ada", "Lovelace")
    # The client's OWN contact details still win — only the name is borrowed.
    assert kwargs["_email"] == "ada@example.com"
    assert kwargs["_phone"] == "+447911123456"


def test_nameless_client_keeps_its_own_country(db: None) -> None:
    from properties.models.geo import Country

    kwargs = ClientLoader().transform(
        _client_row(FirstName="", LastName="", CountryId=24, EnquiryFirstName="Ada")
    )
    assert kwargs is not None
    assert kwargs["country"] == Country.objects.get(iso2="GB")


def test_nameless_client_with_no_enquiry_name_is_still_skipped() -> None:
    assert (
        ClientLoader().transform(
            _client_row(FirstName="", LastName="", EnquiryFirstName=None, EnquiryLastName="   ")
        )
        is None
    )


def test_named_client_ignores_the_enquiry_fallback() -> None:
    kwargs = ClientLoader().transform(
        _client_row(EnquiryFirstName="Grace", EnquiryLastName="Hopper")
    )
    assert kwargs is not None
    assert (kwargs["first_name"], kwargs["last_name"]) == ("Ada", "Lovelace")


def test_client_query_applies_the_lowest_id_named_live_enquiry() -> None:
    query = ClientLoader.legacy_query
    assert "OUTER APPLY" in query
    assert "e.FirstName AS EnquiryFirstName" in query
    assert "e.LastName AS EnquiryLastName" in query
    # Live quotations, live enquiries, a name on the enquiry, lowest Id wins —
    # the one-shot load must be deterministic.
    assert "q.DeletedAt IS NULL" in query
    assert "e.DeletedAt IS NULL" in query
    assert "ORDER BY e.Id" in query
    assert "n.EnquiryFirstName, n.EnquiryLastName" in query


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
        "EnquiryNo": "1501",  # real shape: bare numerics 1501-2176
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


# --- BUG-030 §E: enquiry status, stale leads, person, occupancy, source ---


def test_enquiry_reference_keeps_the_bare_numeric_enquiry_no(db: None) -> None:
    EnquiryLoader()._process_row(_enquiry_db_row(), LoadReport(loader="enquiry"))
    assert Enquiry.objects.get(legacy_id="1").reference == "1501"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, EnquiryStatus.NEW),
        (0, EnquiryStatus.NEW),
        (1, EnquiryStatus.NEW),
        (2, EnquiryStatus.QUOTE_SENT),  # legacy "Completed": the quote e-mail was sent
        (3, EnquiryStatus.QUOTE_SENT),
        (4, EnquiryStatus.PROGRESSING),  # legacy "Opened": a quotation was added
        (5, EnquiryStatus.DEAD),
    ],
)
def test_enquiry_status_follows_the_legacy_meaning(raw: int | None, expected: str) -> None:
    kwargs = EnquiryLoader().transform(_enquiry_row(Status=raw))
    assert kwargs is not None
    assert kwargs["status"] == expected


def test_legacy_enquiry_status_never_maps_to_converted() -> None:
    """A real VillaEnquire row is never CONVERTED (terminal); only BookingLoader's
    `booking-` stand-ins are."""
    for raw in range(10):
        kwargs = EnquiryLoader().transform(_enquiry_row(Status=raw))
        assert kwargs is not None
        assert kwargs["status"] != EnquiryStatus.CONVERTED, raw


def test_enquiry_dead_status_carries_unknown_lost_reason() -> None:
    kwargs = EnquiryLoader().transform(_enquiry_row(Status=5))
    assert kwargs is not None
    assert kwargs["lost_reason"] == EnquiryLostReason.UNKNOWN


def test_enquiry_query_flags_a_live_quotation() -> None:
    query = EnquiryLoader.legacy_query
    assert "FROM VillaEnquire e" in query
    assert (
        "CASE WHEN EXISTS (SELECT 1 FROM VillaQuotationMaster q "
        "WHERE q.EnquireId = e.Id AND q.DeletedAt IS NULL) THEN 1 ELSE 0 END AS HasQuotation"
    ) in query


def test_enquiry_query_skips_soft_deleted_enquiries() -> None:
    # GAP-108: ResProd's `sp_delete_enq` soft-deletes (`DeletedAt`); legacy's
    # `vw_villa_enquire` hides those rows, so the loader must too.
    assert EnquiryLoader.legacy_query.endswith("FROM VillaEnquire e WHERE e.DeletedAt IS NULL")


_NEWEST = datetime(2025, 3, 1, 12, 0)


def _load_enquiries(*rows: dict[str, object]) -> dict[str, Enquiry]:
    report = LoadReport(loader="enquiry")
    # EnquiryNo is the unique reference: one per row, as in the dump.
    EnquiryLoader()._load_rows(
        [{**row, "EnquiryNo": str(1500 + int(str(row["Id"])))} for row in rows], report
    )
    assert report.errors == []
    return {e.legacy_id: e for e in Enquiry.objects.all() if e.legacy_id}


def test_stale_enquiry_without_a_quotation_is_parked_dead_and_cold(db: None) -> None:
    loaded = _load_enquiries(
        _enquiry_db_row(Id=1, Status=1, CreatedAt=_NEWEST),
        _enquiry_db_row(Id=2, Status=None, CreatedAt=_NEWEST - timedelta(days=91)),
    )

    stale = loaded["2"]
    assert (stale.status, stale.lost_reason, stale.lead_status) == (
        EnquiryStatus.DEAD,
        EnquiryLostReason.UNKNOWN,
        LeadStatus.COLD,
    )
    fresh = loaded["1"]
    assert (fresh.status, fresh.lead_status) == (EnquiryStatus.NEW, LeadStatus.WARM)


def test_stale_enquiry_with_a_quotation_keeps_its_mapped_status(db: None) -> None:
    loaded = _load_enquiries(
        _enquiry_db_row(Id=1, Status=1, CreatedAt=_NEWEST),
        _enquiry_db_row(Id=2, Status=4, HasQuotation=1, CreatedAt=_NEWEST - timedelta(days=300)),
    )

    assert (loaded["2"].status, loaded["2"].lead_status) == (
        EnquiryStatus.PROGRESSING,
        LeadStatus.WARM,
    )


def test_stale_cutoff_is_relative_to_the_newest_row_and_exclusive(db: None) -> None:
    loaded = _load_enquiries(
        _enquiry_db_row(Id=1, Status=1, CreatedAt=_NEWEST),
        _enquiry_db_row(Id=2, Status=1, CreatedAt=_NEWEST - timedelta(days=90)),
        _enquiry_db_row(Id=3, Status=1, CreatedAt=None),
    )

    assert loaded["2"].status == EnquiryStatus.NEW  # exactly on the cutoff: not stale
    assert loaded["3"].status == EnquiryStatus.NEW  # undated: no age, no stale rule


def test_transform_without_load_rows_applies_no_stale_rule() -> None:
    kwargs = EnquiryLoader().transform(_enquiry_row(Status=1, CreatedAt=datetime(2001, 1, 1)))
    assert kwargs is not None
    assert kwargs["status"] == EnquiryStatus.NEW
    assert "lead_status" not in kwargs


@pytest.mark.parametrize(("raw", "expected"), [(0, 0), (None, 0), (3, 3)])
def test_enquiry_adults_are_not_fabricated(raw: int | None, expected: int) -> None:
    kwargs = EnquiryLoader().transform(_enquiry_row(Adult=raw))
    assert kwargs is not None
    assert kwargs["adults"] == expected


def test_enquiry_links_the_customer_sharing_its_email(db: None) -> None:
    from accounts.models import PersonEmail

    contact = Person.objects.create(first_name="Ada", last_name="Lovelace", kind=PersonKind.CONTACT)
    PersonEmail.objects.create(contact=contact, email="ada@example.com", is_primary=True)
    customer = Person.objects.create(
        first_name="Ada", last_name="Lovelace", kind=PersonKind.CUSTOMER
    )
    PersonEmail.objects.create(contact=customer, email="ada@example.com", is_primary=True)

    kwargs = EnquiryLoader().transform(_enquiry_row(Email="ADA@example.com"))

    assert kwargs is not None
    assert kwargs["person"] == customer


def test_enquiry_person_is_none_without_an_active_match(db: None) -> None:
    from accounts.models import PersonEmail

    inactive = Person.objects.create(
        first_name="Ada", last_name="Lovelace", status=PersonStatus.INACTIVE
    )
    PersonEmail.objects.create(contact=inactive, email="ada@example.com", is_primary=True)

    assert EnquiryLoader().transform(_enquiry_row(Email="ada@example.com"))["person"] is None  # type: ignore[index]
    assert EnquiryLoader().transform(_enquiry_row(Email=""))["person"] is None  # type: ignore[index]


def test_enquiry_person_needs_agreeing_names(db: None) -> None:
    from accounts.models import PersonEmail

    spouse = Person.objects.create(first_name="Orlando", last_name="Fraser")
    PersonEmail.objects.create(contact=spouse, email="fraser@example.com", is_primary=True)

    kwargs = EnquiryLoader().transform(
        _enquiry_row(Email="fraser@example.com", FirstName="Jane", LastName="Fraser")
    )
    assert kwargs is not None
    assert kwargs["person"] is None


@pytest.mark.parametrize(
    ("country_code", "number", "expected"),
    [
        ("", "07919591288", "+447919591288"),  # BUG-030 §17: GB default
        ("0030", "12345", "+30 12345"),  # invalid number keeps its calling code
    ],
)
def test_enquiry_phone_uses_the_shared_legacy_phone_rule(
    country_code: str, number: str, expected: str
) -> None:
    kwargs = EnquiryLoader().transform(_enquiry_row(CountryCode=country_code, MobileNo=number))
    assert kwargs is not None
    assert kwargs["phone"] == expected


@pytest.mark.parametrize(
    ("created_by", "expected"),
    [
        ("WEBSITE", EnquirySource.MAIN_WEBSITE),
        ("Enquire", EnquirySource.MAIN_WEBSITE),
        (" website ", EnquirySource.MAIN_WEBSITE),
        (None, EnquirySource.MAIN_WEBSITE),
        ("", EnquirySource.MAIN_WEBSITE),
        ("nick@villacollective.com", EnquirySource.OTHER),  # staff-entered
    ],
)
def test_enquiry_site_source_distinguishes_staff_entry(
    created_by: str | None, expected: str
) -> None:
    kwargs = EnquiryLoader().transform(_enquiry_row(CreatedBy=created_by))
    assert kwargs is not None
    assert kwargs["site_source"] == expected
