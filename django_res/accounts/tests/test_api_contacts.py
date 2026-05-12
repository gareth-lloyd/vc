"""API tests for /contacts CRUD + nested emails/phones."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.enums import StaffRole
from accounts.models import Contact, ContactEmail, ContactPhone, User


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        email="staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def contact(db: None) -> Contact:
    return Contact.objects.create(first_name="Ada", last_name="Lovelace")


@pytest.mark.django_db
def test_create_contact(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)

    response = api_client.post(
        "/api/v1/contacts",
        {"first_name": "Grace", "last_name": "Hopper"},
        format="json",
    )

    assert response.status_code == 201
    assert Contact.objects.filter(first_name="Grace").exists()


@pytest.mark.django_db
def test_list_contacts(api_client: APIClient, staff: User, contact: Contact) -> None:
    api_client.force_login(staff)

    response = api_client.get("/api/v1/contacts")

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["results"]}
    assert contact.pk in ids


@pytest.mark.django_db
def test_patch_contact(api_client: APIClient, staff: User, contact: Contact) -> None:
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
def test_add_email_to_contact(api_client: APIClient, staff: User, contact: Contact) -> None:
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
    api_client: APIClient, staff: User, contact: Contact
) -> None:
    old = ContactEmail.objects.create(contact=contact, email="old@x.com", is_primary=True)
    new = ContactEmail.objects.create(contact=contact, email="new@x.com", is_primary=False)
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/contacts/{contact.pk}/emails/{new.pk}:set-primary")

    assert response.status_code == 200
    old.refresh_from_db()
    new.refresh_from_db()
    assert old.is_primary is False
    assert new.is_primary is True


@pytest.mark.django_db
def test_set_primary_phone_demotes_previous(
    api_client: APIClient, staff: User, contact: Contact
) -> None:
    old = ContactPhone.objects.create(contact=contact, number="111", is_primary=True)
    new = ContactPhone.objects.create(contact=contact, number="222", is_primary=False)
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/contacts/{contact.pk}/phones/{new.pk}:set-primary")

    assert response.status_code == 200
    old.refresh_from_db()
    new.refresh_from_db()
    assert old.is_primary is False
    assert new.is_primary is True


@pytest.mark.django_db
def test_invite_portal_returns_501(api_client: APIClient, staff: User, contact: Contact) -> None:
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/contacts/{contact.pk}:invite-portal")

    assert response.status_code == 501
