from __future__ import annotations

from datetime import datetime

import pytest
from django.db import IntegrityError

from accounts.enums import ContactStatus
from accounts.models import Contact, ContactEmail, ContactPhone


@pytest.fixture
def contact(db: None) -> Contact:
    return Contact.objects.create(first_name="Ada", last_name="Lovelace")


@pytest.mark.django_db
def test_contact_email_lowercased() -> None:
    c = Contact.objects.create(first_name="Ada", last_name="Lovelace")
    email = ContactEmail.objects.create(contact=c, email="Ada@EXAMPLE.com")

    email.refresh_from_db()
    assert email.email == "ada@example.com"


@pytest.mark.django_db
def test_only_one_primary_email_per_contact(contact: Contact) -> None:
    ContactEmail.objects.create(contact=contact, email="a@x.com", is_primary=True)

    with pytest.raises(IntegrityError):
        ContactEmail.objects.create(contact=contact, email="b@x.com", is_primary=True)


@pytest.mark.django_db
def test_only_one_primary_phone_per_contact(contact: Contact) -> None:
    ContactPhone.objects.create(contact=contact, number="111", is_primary=True)

    with pytest.raises(IntegrityError):
        ContactPhone.objects.create(contact=contact, number="222", is_primary=True)


@pytest.mark.django_db
def test_anonymize_blanks_pii_and_cascades(contact: Contact) -> None:
    email = ContactEmail.objects.create(contact=contact, email="ada@example.com")
    phone = ContactPhone.objects.create(contact=contact, number="0123 456")

    contact.anonymize()

    contact.refresh_from_db()
    email.refresh_from_db()
    phone.refresh_from_db()
    assert contact.status == ContactStatus.ANONYMIZED
    assert contact.first_name == "[REDACTED]"
    assert contact.last_name == "[REDACTED]"
    assert isinstance(contact.anonymized_at, datetime)
    assert email.email == f"redacted-{email.pk}@anonymized.local"
    assert phone.number == ""


@pytest.mark.django_db
def test_merge_rewrites_fks_and_deletes_source() -> None:
    keep = Contact.objects.create(first_name="Keep", last_name="Me")
    duplicate = Contact.objects.create(first_name="Dup", last_name="Me")
    ContactEmail.objects.create(contact=duplicate, email="dup@example.com")
    duplicate.merge(keep)

    assert not Contact.objects.filter(pk=duplicate.pk).exists()
    assert keep.emails.filter(email="dup@example.com").exists()
