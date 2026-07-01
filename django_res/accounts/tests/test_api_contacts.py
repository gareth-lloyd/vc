"""API tests for /contacts CRUD + nested emails/phones."""

from __future__ import annotations

from typing import cast

import pytest
from rest_framework.test import APIClient

from accounts.enums import PersonKind, PersonStatus, PersonTag
from accounts.factories import OrganisationFactory
from accounts.models import Organisation, Person, PersonEmail, PersonPhone, User
from core.enums import StaffRole


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def admin(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="admin@example.com",
        password="x",
        role=StaffRole.ADMIN,
    )


@pytest.fixture
def contact(db: None) -> Person:
    return Person.objects.create(first_name="Ada", last_name="Lovelace")


@pytest.mark.django_db
def test_create_contact(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/contacts",
        {
            "first_name": "Grace",
            "last_name": "Hopper",
            "emails": [{"email": "grace@example.com", "is_primary": True}],
        },
        format="json",
    )

    assert response.status_code == 201
    person = Person.objects.get(first_name="Grace")
    assert person.emails.filter(email="grace@example.com", is_primary=True).exists()


@pytest.mark.django_db
def test_create_contact_with_inline_phone(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/contacts",
        {
            "first_name": "Grace",
            "last_name": "Hopper",
            "phones": [{"number": "+441234567890"}],
        },
        format="json",
    )

    assert response.status_code == 201
    person = Person.objects.get(first_name="Grace")
    assert person.phones.filter(number="+441234567890").exists()


@pytest.mark.django_db
def test_create_active_contact_without_channel_is_rejected(
    api_client: APIClient, staff: User
) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/contacts",
        {"first_name": "Grace", "last_name": "Hopper"},
        format="json",
    )

    assert response.status_code == 400
    assert not Person.objects.filter(first_name="Grace").exists()


@pytest.mark.django_db
def test_create_inactive_contact_without_channel_is_allowed(
    api_client: APIClient, staff: User
) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/contacts",
        {"first_name": "Grace", "last_name": "Hopper", "status": "inactive"},
        format="json",
    )

    assert response.status_code == 201
    assert Person.objects.filter(first_name="Grace").exists()


@pytest.mark.django_db
def test_create_contact_with_two_primary_emails_is_rejected(
    api_client: APIClient, staff: User
) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/contacts",
        {
            "first_name": "Grace",
            "last_name": "Hopper",
            "emails": [
                {"email": "a@example.com", "is_primary": True},
                {"email": "b@example.com", "is_primary": True},
            ],
        },
        format="json",
    )

    assert response.status_code == 400
    assert not Person.objects.filter(first_name="Grace").exists()


@pytest.mark.django_db
def test_create_agency_only_contact_is_allowed(api_client: APIClient, staff: User) -> None:
    """GAP-029: a company/agency-only contact (no personal name) must create.

    Mirrors the FE `contactWriteInputSchema` "name OR agency" refine — the
    2026-06-11 owner email confirmed company must not be required *and* names
    must not be mandatory when an agency stands in for them.
    """
    agency = cast(Organisation, OrganisationFactory(name="Acme Villas Ltd"))
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/contacts",
        {
            "agency": agency.pk,
            "emails": [{"email": "bookings@acme.example", "is_primary": True}],
        },
        format="json",
    )

    assert response.status_code == 201, response.json()
    person = Person.objects.get(agency=agency)
    assert person.first_name == ""
    assert person.last_name == ""


@pytest.mark.django_db
def test_create_contact_without_name_or_agency_is_rejected(
    api_client: APIClient, staff: User
) -> None:
    """GAP-029: loosening the model must not let a nameless, agency-less contact
    through — the serializer floor rejects it with a `first_name` field error."""
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/contacts",
        {"emails": [{"email": "who@example.com", "is_primary": True}]},
        format="json",
    )

    assert response.status_code == 400
    assert "first_name" in response.json()["field_errors"]
    assert not Person.objects.filter(emails__email="who@example.com").exists()


@pytest.mark.django_db
def test_patch_clear_names_with_agency_allowed(api_client: APIClient, staff: User) -> None:
    """GAP-029: clearing both names on an edit is fine while an agency remains —
    the guard reads the effective (attrs over instance) agency, not just the payload."""
    agency = cast(Organisation, OrganisationFactory(name="Bell Labs"))
    person = Person.objects.create(first_name="Ada", last_name="Lovelace", agency=agency)
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/contacts/{person.pk}",
        {"first_name": "", "last_name": ""},
        format="json",
    )

    assert response.status_code == 200, response.json()
    person.refresh_from_db()
    assert person.first_name == ""
    assert person.last_name == ""
    assert person.agency_id == agency.pk


@pytest.mark.django_db
def test_patch_clear_names_without_agency_rejected(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    """GAP-029: clearing both names on an agency-less contact is rejected —
    a contact stripped of every identifier is not allowed."""
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/contacts/{contact.pk}",
        {"first_name": "", "last_name": ""},
        format="json",
    )

    assert response.status_code == 400
    assert "first_name" in response.json()["field_errors"]
    contact.refresh_from_db()
    assert contact.first_name == "Ada"


@pytest.mark.django_db
def test_patch_channelless_active_contact_notes_still_allowed(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    """Editing a legacy channel-less active contact in place must stay allowed —
    contactability only guards the create and the status→active transition."""
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/contacts/{contact.pk}",
        {"notes": "called, no answer"},
        format="json",
    )

    assert response.status_code == 200
    contact.refresh_from_db()
    assert contact.notes == "called, no answer"


@pytest.mark.django_db
def test_reactivating_channelless_contact_is_rejected(api_client: APIClient, staff: User) -> None:
    inactive = Person.objects.create(first_name="Grace", last_name="Hopper", status="inactive")
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/contacts/{inactive.pk}",
        {"status": "active"},
        format="json",
    )

    assert response.status_code == 400
    inactive.refresh_from_db()
    assert inactive.status == "inactive"


@pytest.mark.django_db
def test_reactivating_contact_with_existing_channel_is_allowed(
    api_client: APIClient, staff: User
) -> None:
    inactive = Person.objects.create(first_name="Grace", last_name="Hopper", status="inactive")
    PersonEmail.objects.create(contact=inactive, email="grace@example.com")
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/contacts/{inactive.pk}",
        {"status": "active"},
        format="json",
    )

    assert response.status_code == 200
    inactive.refresh_from_db()
    assert inactive.status == "active"


@pytest.mark.django_db
def test_delete_last_channel_of_active_contact_is_rejected(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    email = PersonEmail.objects.create(contact=contact, email="ada@example.com")
    api_client.force_login(staff)

    response = api_client.delete(f"/api/v1/contacts/{contact.pk}/emails/{email.pk}")

    assert response.status_code == 400
    assert contact.emails.filter(pk=email.pk).exists()


@pytest.mark.django_db
def test_delete_channel_when_another_remains_succeeds(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    email = PersonEmail.objects.create(contact=contact, email="ada@example.com")
    PersonPhone.objects.create(contact=contact, number="+441234567890")
    api_client.force_login(staff)

    response = api_client.delete(f"/api/v1/contacts/{contact.pk}/emails/{email.pk}")

    assert response.status_code == 204
    assert not contact.emails.filter(pk=email.pk).exists()


@pytest.mark.django_db
def test_delete_last_channel_of_inactive_contact_succeeds(
    api_client: APIClient, staff: User
) -> None:
    inactive = Person.objects.create(first_name="Grace", last_name="Hopper", status="inactive")
    email = PersonEmail.objects.create(contact=inactive, email="grace@example.com")
    api_client.force_login(staff)

    response = api_client.delete(f"/api/v1/contacts/{inactive.pk}/emails/{email.pk}")

    assert response.status_code == 204
    assert not inactive.emails.filter(pk=email.pk).exists()


@pytest.mark.django_db
def test_list_contacts(api_client: APIClient, staff: User, contact: Person) -> None:
    api_client.force_login(staff)

    response = api_client.get("/api/v1/contacts")

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["results"]}
    assert contact.pk in ids


@pytest.mark.django_db
def test_list_contacts_includes_customer_persons(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    # GAP-045 D2: `/contacts` is now a kind-aware directory of ALL Persons —
    # customers (the former excluded Guest mirrors) appear too.
    api_client.force_login(staff)
    customer = Person.objects.create(
        first_name="Tom", last_name="Traveller", legacy_id="guest-42", kind=PersonKind.CUSTOMER
    )

    response = api_client.get("/api/v1/contacts")

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["results"]}
    assert contact.pk in ids
    assert customer.pk in ids


@pytest.mark.django_db
def test_retrieve_customer_person_returns_200(api_client: APIClient, staff: User) -> None:
    # GAP-045 D2: a customer Person (was a `guest-` mirror) is now retrievable —
    # previously the exclusion made it 404.
    api_client.force_login(staff)
    customer = Person.objects.create(
        first_name="Tom", last_name="Traveller", legacy_id="guest-43", kind=PersonKind.CUSTOMER
    )

    response = api_client.get(f"/api/v1/contacts/{customer.pk}")

    assert response.status_code == 200
    assert response.json()["kind"] == PersonKind.CUSTOMER.value


@pytest.mark.django_db
def test_filter_contacts_by_kind(api_client: APIClient, staff: User, contact: Person) -> None:
    # `contact` defaults to CONTACT; add a CUSTOMER. `?kind=` narrows; no param = all.
    api_client.force_login(staff)
    customer = Person.objects.create(
        first_name="Tom", last_name="Traveller", kind=PersonKind.CUSTOMER
    )

    both = {row["id"] for row in api_client.get("/api/v1/contacts").json()["results"]}
    assert {contact.pk, customer.pk} <= both

    customers = api_client.get("/api/v1/contacts?kind=customer").json()["results"]
    assert {row["id"] for row in customers} == {customer.pk}

    contacts = api_client.get("/api/v1/contacts?kind=contact").json()["results"]
    assert customer.pk not in {row["id"] for row in contacts}
    assert contact.pk in {row["id"] for row in contacts}


@pytest.mark.django_db
def test_create_customer_contact_sets_kind(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/contacts",
        {
            "first_name": "New",
            "last_name": "Customer",
            "kind": PersonKind.CUSTOMER.value,
            "emails": [{"email": "new@example.com", "is_primary": True}],
        },
        format="json",
    )

    assert response.status_code == 201
    person = Person.objects.get(pk=response.json()["id"])
    assert person.kind == PersonKind.CUSTOMER.value


@pytest.mark.django_db
def test_create_contact_defaults_kind_contact(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/contacts",
        {
            "first_name": "New",
            "last_name": "Owner",
            "emails": [{"email": "owner@example.com", "is_primary": True}],
        },
        format="json",
    )

    assert response.status_code == 201
    assert Person.objects.get(pk=response.json()["id"]).kind == PersonKind.CONTACT.value


@pytest.mark.django_db
def test_patch_cannot_change_kind(api_client: APIClient, staff: User, contact: Person) -> None:
    # `kind` is create-only: a PATCH must not reclassify a contact.
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/contacts/{contact.pk}",
        {"kind": PersonKind.CUSTOMER.value},
        format="json",
    )

    assert response.status_code == 200
    contact.refresh_from_db()
    assert contact.kind == PersonKind.CONTACT.value


@pytest.mark.django_db
def test_patch_contact(api_client: APIClient, staff: User, contact: Person) -> None:
    # GAP-046: free-text `company` is gone; a contact's employer is the
    # structured `agency` FK, set by PK.
    agency = cast(Organisation, OrganisationFactory(name="Bell Labs"))
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/contacts/{contact.pk}",
        {"agency": agency.pk},
        format="json",
    )

    assert response.status_code == 200
    contact.refresh_from_db()
    assert contact.agency_id == agency.pk


@pytest.mark.django_db
def test_get_contact_includes_tags(api_client: APIClient, staff: User, contact: Person) -> None:
    contact.tags = [PersonTag.VIP]
    contact.save(update_fields=["tags"])
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/contacts/{contact.pk}")

    assert response.status_code == 200
    assert response.json()["tags"] == ["vip"]


@pytest.mark.django_db
def test_get_contact_includes_address_and_country_name(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    # GAP-042: the 360 profile surfaces town/post_code plus the country name
    # (the FK pk alone is useless to the sales team).
    from properties.models import Country

    country, _ = Country.objects.get_or_create(
        iso2="QX", defaults={"iso3": "QXX", "name": "Testopia"}
    )
    contact.town = "Athens"
    contact.post_code = "10557"
    contact.country = country
    contact.save(update_fields=["town", "post_code", "country"])
    api_client.force_login(staff)

    body = api_client.get(f"/api/v1/contacts/{contact.pk}").json()

    assert body["town"] == "Athens"
    assert body["post_code"] == "10557"
    assert body["country"] == country.pk
    assert body["country_name"] == "Testopia"


@pytest.mark.django_db
def test_patch_contact_round_trips_town_and_postcode(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/contacts/{contact.pk}",
        {"town": "Bath", "post_code": "BA1 1AA"},
        format="json",
    )

    assert response.status_code == 200
    contact.refresh_from_db()
    assert contact.town == "Bath"
    assert contact.post_code == "BA1 1AA"


@pytest.mark.django_db
def test_patch_contact_can_change_country(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    # GAP-052: country is now operator-editable via a picker (overturns the
    # GAP-042 display-only interim).
    from properties.models import Country

    country, _ = Country.objects.get_or_create(
        iso2="QY", defaults={"iso3": "QYY", "name": "Testlandia"}
    )
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/contacts/{contact.pk}",
        {"country": country.pk},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["country"] == country.pk
    assert response.json()["country_name"] == "Testlandia"
    contact.refresh_from_db()
    assert contact.country_id == country.pk


@pytest.mark.django_db
def test_patch_contact_can_clear_country(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    # GAP-052: country is nullable — clearing it is a valid edit.
    from properties.models import Country

    country, _ = Country.objects.get_or_create(
        iso2="QZ", defaults={"iso3": "QZZ", "name": "Testovia"}
    )
    contact.country = country
    contact.save(update_fields=["country"])
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/contacts/{contact.pk}",
        {"country": None},
        format="json",
    )

    assert response.status_code == 200
    contact.refresh_from_db()
    assert contact.country_id is None


@pytest.mark.django_db
def test_patch_country_is_audited(api_client: APIClient, staff: User, contact: Person) -> None:
    # GAP-052: editing country leaves an AuditLog trail (the FK pk, not the
    # unserializable Country instance — tracked as `country_id`).
    from django.contrib.contenttypes.models import ContentType

    from core.models import AuditLog
    from properties.models import Country

    country, _ = Country.objects.get_or_create(
        iso2="QW", defaults={"iso3": "QWW", "name": "Testburg"}
    )
    api_client.force_login(staff)
    api_client.patch(
        f"/api/v1/contacts/{contact.pk}",
        {"country": country.pk},
        format="json",
    )

    ct = ContentType.objects.get_for_model(Person)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(contact.pk))
    assert any(r.field_diffs.get("country_id") == [None, country.pk] for r in rows)


@pytest.mark.django_db
def test_contact_types_surfaces_customer_and_property_role(
    api_client: APIClient, staff: User
) -> None:
    # GAP-052: a person can wear several hats — surface every one. A CUSTOMER
    # who is also a property OWNER shows both, sorted.
    from accounts.enums import ContactRole
    from properties.factories import PropertyContactAssignmentFactory

    person = Person.objects.create(
        first_name="Dual", last_name="Hat", kind=PersonKind.CUSTOMER.value
    )
    PropertyContactAssignmentFactory(contact=person, role=ContactRole.OWNER)
    api_client.force_login(staff)

    body = api_client.get(f"/api/v1/contacts/{person.pk}").json()

    assert body["contact_types"] == ["customer", "owner"]


@pytest.mark.django_db
def test_contact_types_includes_agent_for_agency_member(api_client: APIClient, staff: User) -> None:
    # GAP-052/046: belonging to an agency makes a contact an Agent.
    agency = cast(Organisation, OrganisationFactory())
    person = Person.objects.create(
        first_name="Aggie", last_name="Agent", kind=PersonKind.CONTACT.value, agency=agency
    )
    api_client.force_login(staff)

    body = api_client.get(f"/api/v1/contacts/{person.pk}").json()

    assert body["contact_types"] == ["agent"]


@pytest.mark.django_db
def test_contact_types_empty_for_plain_contact(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    # A bare CONTACT with no bookings, agency, or property role has no type.
    contact.kind = PersonKind.CONTACT.value
    contact.save(update_fields=["kind"])
    api_client.force_login(staff)

    body = api_client.get(f"/api/v1/contacts/{contact.pk}").json()

    assert body["contact_types"] == []


@pytest.mark.django_db
def test_contact_types_dedupes_role_and_active_only(api_client: APIClient, staff: User) -> None:
    # Only ACTIVE (end_date IS NULL) assignments count; an ended role drops off.
    from datetime import date

    from accounts.enums import ContactRole
    from properties.factories import PropertyContactAssignmentFactory

    person = Person.objects.create(
        first_name="Past", last_name="Manager", kind=PersonKind.CONTACT.value
    )
    PropertyContactAssignmentFactory(contact=person, role=ContactRole.MANAGER)
    PropertyContactAssignmentFactory(
        contact=person, role=ContactRole.OWNER, end_date=date(2020, 1, 1)
    )
    api_client.force_login(staff)

    body = api_client.get(f"/api/v1/contacts/{person.pk}").json()

    assert body["contact_types"] == ["manager"]


@pytest.mark.django_db
def test_retrieve_contact_types_is_query_pinned(api_client: APIClient, staff: User) -> None:
    # GAP-052: contact_types rides a correlated Subquery, not a per-row fetch —
    # query count stays flat regardless of how many active assignments exist.
    from accounts.enums import ContactRole
    from core.tests import assert_max_queries
    from properties.factories import PropertyContactAssignmentFactory

    person = Person.objects.create(
        first_name="Many", last_name="Roles", kind=PersonKind.CUSTOMER.value
    )
    for role in (ContactRole.OWNER, ContactRole.MANAGER, ContactRole.HOUSEKEEPER):
        PropertyContactAssignmentFactory(contact=person, role=role)
    api_client.force_login(staff)

    with assert_max_queries(8):
        api_client.get(f"/api/v1/contacts/{person.pk}")


@pytest.mark.django_db
def test_list_contact_types_query_count_is_flat(api_client: APIClient, staff: User) -> None:
    # GAP-052: the active_roles subquery must NOT cross-join the booking_count
    # Count — list query count stays flat (and the paginator COUNT accurate)
    # whether one or many contacts each hold several roles.
    from accounts.enums import ContactRole
    from core.tests import assert_max_queries
    from properties.factories import PropertyContactAssignmentFactory

    def make(n: int) -> Person:
        p = Person.objects.create(
            first_name=f"C{n}", last_name="Roles", kind=PersonKind.CUSTOMER.value
        )
        for role in (ContactRole.OWNER, ContactRole.MANAGER):
            PropertyContactAssignmentFactory(contact=p, role=role)
        return p

    api_client.force_login(staff)
    make(1)
    with assert_max_queries(8):
        first = api_client.get("/api/v1/contacts").json()
    for n in range(2, 6):
        make(n)
    with assert_max_queries(8):
        many = api_client.get("/api/v1/contacts").json()

    assert first["count"] == 1
    assert many["count"] == 5  # COUNT not inflated by roles
    assert sorted(many["results"][0]["contact_types"]) == ["customer", "manager", "owner"]


@pytest.mark.django_db
def test_get_contact_without_bookings_is_not_repeat(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    api_client.force_login(staff)

    body = api_client.get(f"/api/v1/contacts/{contact.pk}").json()

    assert body["booking_count"] == 0
    assert body["is_repeat_customer"] is False


@pytest.mark.django_db
def test_patch_contact_sets_tags(api_client: APIClient, staff: User, contact: Person) -> None:
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/contacts/{contact.pk}",
        {"tags": ["vip", "trade"]},
        format="json",
    )

    assert response.status_code == 200
    contact.refresh_from_db()
    # Model save() canonicalizes to sorted+deduped.
    assert contact.tags == ["trade", "vip"]
    assert response.json()["tags"] == ["trade", "vip"]


@pytest.mark.django_db
def test_patch_contact_rejects_unknown_tag(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/contacts/{contact.pk}",
        {"tags": ["vip", "not_a_real_tag"]},
        format="json",
    )

    assert response.status_code == 400
    assert "tags" in response.json()["field_errors"]
    contact.refresh_from_db()
    assert contact.tags == []


@pytest.mark.django_db
def test_create_contact_with_tags(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/contacts",
        {
            "first_name": "Vee",
            "last_name": "Eye-Pee",
            "tags": ["vip"],
            "emails": [{"email": "vip@example.com", "is_primary": True}],
        },
        format="json",
    )

    assert response.status_code == 201
    assert Person.objects.get(pk=response.json()["id"]).tags == ["vip"]


@pytest.mark.django_db
def test_filter_contacts_by_tags(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)
    vip = Person.objects.create(first_name="V", last_name="One", tags=[PersonTag.VIP])
    trade = Person.objects.create(first_name="T", last_name="Two", tags=[PersonTag.TRADE])
    Person.objects.create(first_name="N", last_name="None")

    rows = api_client.get("/api/v1/contacts?tags=vip").json()["results"]
    assert {r["id"] for r in rows} == {vip.pk}

    # Overlap: a comma list matches a person carrying ANY of the tags.
    rows = api_client.get("/api/v1/contacts?tags=vip,trade").json()["results"]
    assert {r["id"] for r in rows} == {vip.pk, trade.pk}


@pytest.mark.django_db
def test_filter_contacts_by_tags_ignores_unknown_token(api_client: APIClient, staff: User) -> None:
    """An unknown token is dropped, not 400'd; a known token still filters.
    An all-garbage value is ignored (returns the unfiltered list), never a
    silent empty page."""
    api_client.force_login(staff)
    vip = Person.objects.create(first_name="V", last_name="One", tags=[PersonTag.VIP])
    plain = Person.objects.create(first_name="N", last_name="None")

    mixed = api_client.get("/api/v1/contacts?tags=vip,bogus").json()["results"]
    assert {r["id"] for r in mixed} == {vip.pk}

    garbage = api_client.get("/api/v1/contacts?tags=bogus").json()["results"]
    assert {vip.pk, plain.pk} <= {r["id"] for r in garbage}


@pytest.mark.django_db
def test_patch_tags_is_audited(api_client: APIClient, staff: User, contact: Person) -> None:
    from django.contrib.contenttypes.models import ContentType

    from core.models import AuditLog

    api_client.force_login(staff)
    api_client.patch(
        f"/api/v1/contacts/{contact.pk}",
        {"tags": ["vip"]},
        format="json",
    )

    ct = ContentType.objects.get_for_model(Person)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(contact.pk))
    assert any(r.field_diffs.get("tags") == [[], ["vip"]] for r in rows)


@pytest.mark.django_db
def test_add_email_to_contact(api_client: APIClient, staff: User, contact: Person) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/contacts/{contact.pk}/emails",
        {"email": "ada@example.com", "label": "primary", "is_primary": True},
        format="json",
    )

    assert response.status_code == 201
    assert contact.emails.filter(email="ada@example.com", is_primary=True).exists()


@pytest.mark.django_db
def test_set_primary_email_demotes_previous(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    old = PersonEmail.objects.create(contact=contact, email="old@x.com", is_primary=True)
    new = PersonEmail.objects.create(contact=contact, email="new@x.com", is_primary=False)
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/contacts/{contact.pk}/emails/{new.pk}:set-primary")

    assert response.status_code == 200
    old.refresh_from_db()
    new.refresh_from_db()
    assert old.is_primary is False
    assert new.is_primary is True


@pytest.mark.django_db
def test_set_primary_phone_demotes_previous(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    old = PersonPhone.objects.create(contact=contact, number="111", is_primary=True)
    new = PersonPhone.objects.create(contact=contact, number="222", is_primary=False)
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/contacts/{contact.pk}/phones/{new.pk}:set-primary")

    assert response.status_code == 200
    old.refresh_from_db()
    new.refresh_from_db()
    assert old.is_primary is False
    assert new.is_primary is True


@pytest.mark.django_db
def test_invite_portal_returns_501(api_client: APIClient, staff: User, contact: Person) -> None:
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/contacts/{contact.pk}:invite-portal")

    assert response.status_code == 501


@pytest.mark.django_db
def test_delete_contact_referenced_by_protected_fk_returns_409(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    # A contact assigned to a property is referenced through a PROTECT FK;
    # deleting it must surface a clean 409, not an uncaught 500.
    from properties.factories import PropertyContactAssignmentFactory

    PropertyContactAssignmentFactory(contact=contact)
    api_client.force_login(staff)

    response = api_client.delete(f"/api/v1/contacts/{contact.pk}")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "protected"
    assert Person.objects.filter(pk=contact.pk).exists()


@pytest.mark.django_db
def test_delete_unreferenced_contact_succeeds(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    api_client.force_login(staff)

    response = api_client.delete(f"/api/v1/contacts/{contact.pk}")

    assert response.status_code == 204
    assert not Person.objects.filter(pk=contact.pk).exists()


# ----------------------------------------------------------------------
# GAP-045 Unit 3c-3d — :merge + :anonymize colon-verbs (real contacts only)
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_merge_requires_admin(api_client: APIClient, staff: User, contact: Person) -> None:
    target = Person.objects.create(first_name="Target", last_name="Person")
    api_client.force_login(staff)

    response = api_client.post(
        f"/api/v1/contacts/{contact.pk}:merge",
        {"target_contact_id": target.pk},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_anonymize_requires_admin(api_client: APIClient, staff: User, contact: Person) -> None:
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/contacts/{contact.pk}:anonymize")

    assert response.status_code == 403


@pytest.mark.django_db
def test_merge_moves_relations_and_deletes_source(
    api_client: APIClient, admin: User, contact: Person
) -> None:
    """A whole-person merge folds BOTH a customer relation and an agent relation
    into the target, then hard-deletes the source."""
    from reservations.models import Enquiry

    target = Person.objects.create(first_name="Target", last_name="Person")
    as_customer = Enquiry.objects.create(person=contact)
    as_agent = Enquiry.objects.create(agent=contact)
    api_client.force_login(admin)

    response = api_client.post(
        f"/api/v1/contacts/{contact.pk}:merge",
        {"target_contact_id": target.pk},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["id"] == target.pk
    assert not Person.objects.filter(pk=contact.pk).exists()
    as_customer.refresh_from_db()
    as_agent.refresh_from_db()
    assert as_customer.person_id == target.pk
    assert as_agent.agent_id == target.pk


@pytest.mark.django_db
def test_merge_into_self_returns_400(api_client: APIClient, admin: User, contact: Person) -> None:
    api_client.force_login(admin)

    response = api_client.post(
        f"/api/v1/contacts/{contact.pk}:merge",
        {"target_contact_id": contact.pk},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "merge_invalid"


@pytest.mark.django_db
def test_merge_customer_source_into_contact_succeeds(
    api_client: APIClient, admin: User, contact: Person
) -> None:
    """GAP-045 D5: Guest is retired, so a customer Person merges through the verb
    like any other Person — dedup customers via /contacts (Person.merge)."""
    customer = Person.objects.create(
        first_name="Tom", last_name="Traveller", legacy_id="client-7", kind=PersonKind.CUSTOMER
    )
    api_client.force_login(admin)

    response = api_client.post(
        f"/api/v1/contacts/{customer.pk}:merge",
        {"target_contact_id": contact.pk},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["id"] == contact.pk
    assert not Person.objects.filter(pk=customer.pk).exists()


@pytest.mark.django_db
def test_merge_contact_into_customer_target_succeeds(
    api_client: APIClient, admin: User, contact: Person
) -> None:
    """The target may be a customer Person too — both legs resolve through the
    unfiltered Person queryset now (GAP-045 D5)."""
    customer = Person.objects.create(
        first_name="Tom", last_name="Traveller", legacy_id="client-8", kind=PersonKind.CUSTOMER
    )
    api_client.force_login(admin)

    response = api_client.post(
        f"/api/v1/contacts/{contact.pk}:merge",
        {"target_contact_id": customer.pk},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["id"] == customer.pk
    assert not Person.objects.filter(pk=contact.pk).exists()


@pytest.mark.django_db
def test_anonymize_customer_person_succeeds(api_client: APIClient, admin: User) -> None:
    """GAP-045 D5: a customer Person can be anonymized through the verb."""
    customer = Person.objects.create(
        first_name="Tom", last_name="Traveller", legacy_id="client-9", kind=PersonKind.CUSTOMER
    )
    api_client.force_login(admin)

    response = api_client.post(f"/api/v1/contacts/{customer.pk}:anonymize")

    assert response.status_code == 200
    customer.refresh_from_db()
    assert customer.status == PersonStatus.ANONYMIZED.value
    assert customer.first_name == "[REDACTED]"


@pytest.mark.django_db
def test_anonymize_redacts_and_is_idempotent_without_leaking_pii(
    api_client: APIClient, admin: User, contact: Person
) -> None:
    PersonEmail.objects.create(contact=contact, email="ada@example.com", is_primary=True)
    api_client.force_login(admin)

    first = api_client.post(f"/api/v1/contacts/{contact.pk}:anonymize")

    assert first.status_code == 200
    contact.refresh_from_db()
    assert contact.status == PersonStatus.ANONYMIZED.value
    assert contact.first_name == "[REDACTED]"
    # No cleartext PII in the 200 body — emails are rewritten to the
    # `redacted-…@anonymized.local` sentinel, not the original address.
    blob = first.content.decode()
    assert "ada@example.com" not in blob
    assert "Lovelace" not in blob

    # Idempotent: running again leaves the redacted state intact.
    second = api_client.post(f"/api/v1/contacts/{contact.pk}:anonymize")

    assert second.status_code == 200
    contact.refresh_from_db()
    assert contact.status == PersonStatus.ANONYMIZED.value


# ----------------------------------------------------------------------
# GAP-046 Unit 2 — Person.agency on the contact API
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_create_contact_with_agency(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)
    agency = cast(Organisation, OrganisationFactory(name="Dune Travel"))

    response = api_client.post(
        "/api/v1/contacts",
        {
            "first_name": "Grace",
            "last_name": "Hopper",
            "agency": agency.pk,
            "emails": [{"email": "grace@example.com", "is_primary": True}],
        },
        format="json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["agency"] == agency.pk
    assert body["agency_detail"]["name"] == "Dune Travel"
    assert Person.objects.get(first_name="Grace").agency_id == agency.pk


@pytest.mark.django_db
def test_patch_contact_sets_and_clears_agency(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    api_client.force_login(staff)
    agency = cast(Organisation, OrganisationFactory())

    set_resp = api_client.patch(
        f"/api/v1/contacts/{contact.pk}",
        {"agency": agency.pk},
        format="json",
    )
    assert set_resp.status_code == 200
    contact.refresh_from_db()
    assert contact.agency_id == agency.pk

    clear_resp = api_client.patch(
        f"/api/v1/contacts/{contact.pk}",
        {"agency": None},
        format="json",
    )
    assert clear_resp.status_code == 200
    contact.refresh_from_db()
    assert contact.agency_id is None


@pytest.mark.django_db
def test_search_contacts_by_agency_name(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)
    dune = cast(Organisation, OrganisationFactory(name="Dune Travel Co"))
    other = cast(Organisation, OrganisationFactory(name="Sandpiper Holidays"))
    Person.objects.create(first_name="A", last_name="One", agency=dune)
    Person.objects.create(first_name="B", last_name="Two", agency=other)

    results = api_client.get("/api/v1/contacts?search=Dune").json()["results"]

    names = {row["agency_detail"]["name"] for row in results if row["agency_detail"]}
    assert names == {"Dune Travel Co"}


# --- GAP-048 L2-3: Suppliers directory scoping ------------------------------


@pytest.mark.django_db
def test_directory_suppliers_excludes_agents_and_customers(
    api_client: APIClient, staff: User
) -> None:
    """`?directory=suppliers` = operator-side `kind=CONTACT` people MINUS
    agent-capacity (agency members and active agent-role assignees). Only the
    `kind=CUSTOMER` classification is excluded — a kind=CONTACT person who has
    booked a stay is still a supplier. A plain contact with no property role
    still appears — a contact must not vanish between creation and assignment
    (GAP-048 decision)."""
    from accounts.enums import ContactRole
    from properties.factories import PropertyContactAssignmentFactory

    api_client.force_login(staff)

    plain = Person.objects.create(first_name="Sup", last_name="Plain", kind=PersonKind.CONTACT)
    housekeeper = Person.objects.create(
        first_name="Hank", last_name="House", kind=PersonKind.CONTACT
    )
    PropertyContactAssignmentFactory(contact=housekeeper, role=ContactRole.HOUSEKEEPER)

    agency = cast(Organisation, OrganisationFactory())
    agency_member = Person.objects.create(
        first_name="Aggie", last_name="Agent", kind=PersonKind.CONTACT, agency=agency
    )
    role_agent = Person.objects.create(
        first_name="Role", last_name="Agent", kind=PersonKind.CONTACT
    )
    PropertyContactAssignmentFactory(contact=role_agent, role=ContactRole.AGENT)

    customer = Person.objects.create(first_name="Cust", last_name="Omer", kind=PersonKind.CUSTOMER)

    ids = {
        row["id"]
        for row in api_client.get("/api/v1/contacts?directory=suppliers").json()["results"]
    }
    assert {plain.pk, housekeeper.pk} <= ids
    assert ids.isdisjoint({agency_member.pk, role_agent.pk, customer.pk})


@pytest.mark.django_db
def test_directory_suppliers_excludes_ended_agent_role(api_client: APIClient, staff: User) -> None:
    """Only an ACTIVE agent assignment confers agent-capacity. A contact whose
    agent role was ended (`end_date` set) is operator-side again → a supplier."""
    from datetime import date

    from accounts.enums import ContactRole
    from properties.factories import PropertyContactAssignmentFactory

    api_client.force_login(staff)
    former_agent = Person.objects.create(
        first_name="Gone", last_name="Agent", kind=PersonKind.CONTACT
    )
    PropertyContactAssignmentFactory(
        contact=former_agent, role=ContactRole.AGENT, end_date=date(2024, 1, 1)
    )

    ids = {
        row["id"]
        for row in api_client.get("/api/v1/contacts?directory=suppliers").json()["results"]
    }
    assert former_agent.pk in ids


@pytest.mark.django_db
def test_directory_suppliers_query_count_is_flat(api_client: APIClient, staff: User) -> None:
    """The directory exclusion is a NOT-EXISTS subquery, not a JOIN — the list
    query count stays flat regardless of how many suppliers/roles exist."""
    from accounts.enums import ContactRole
    from core.tests import assert_max_queries
    from properties.factories import PropertyContactAssignmentFactory

    def make(n: int) -> Person:
        p = Person.objects.create(first_name=f"S{n}", last_name="Sup", kind=PersonKind.CONTACT)
        PropertyContactAssignmentFactory(contact=p, role=ContactRole.HOUSEKEEPER)
        return p

    api_client.force_login(staff)
    make(1)
    with assert_max_queries(8):
        first = api_client.get("/api/v1/contacts?directory=suppliers").json()
    for n in range(2, 6):
        make(n)
    with assert_max_queries(8):
        many = api_client.get("/api/v1/contacts?directory=suppliers").json()

    assert first["count"] == 1
    assert many["count"] == 5  # COUNT not inflated by the exclusion subquery
