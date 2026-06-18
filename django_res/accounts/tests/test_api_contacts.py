"""API tests for /contacts CRUD + nested emails/phones."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import Person, PersonEmail, PersonPhone, User
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
def test_list_contacts_excludes_guest_backfilled_persons(
    api_client: APIClient, staff: User, contact: Person
) -> None:
    # GAP-045 Unit 3b: Persons back-filled from reservations.Guest carry a
    # `guest-` legacy_id and must not leak into the owner/agent directory.
    api_client.force_login(staff)
    guest_person = Person.objects.create(
        first_name="Tom", last_name="Traveller", legacy_id="guest-42"
    )

    response = api_client.get("/api/v1/contacts")

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["results"]}
    assert contact.pk in ids
    assert guest_person.pk not in ids


@pytest.mark.django_db
def test_patch_contact(api_client: APIClient, staff: User, contact: Person) -> None:
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/contacts/{contact.pk}",
        {"company": "Bell Labs"},
        format="json",
    )

    assert response.status_code == 200
    contact.refresh_from_db()
    assert contact.company == "Bell Labs"


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
