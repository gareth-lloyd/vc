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
