"""GAP-045 Unit 3c-1a — the Guest → Person mirror (`person_sync` service + the
`reservations.signals._guest_post_save` signal that drives it).

Saving a Guest must keep its unified `accounts.Person` (keyed
`legacy_id="guest-{pk}"`) in lockstep, reconciling the single email/phone into a
PRIMARY child *in place* so a later edit never duplicates a channel.
"""

from __future__ import annotations

from typing import cast

import pytest

from accounts.models import Person, PersonEmail, PersonPhone
from reservations.enums import ContactMethod, GuestStatus
from reservations.factories import GuestFactory
from reservations.models import Guest
from reservations.services.person_sync import person_for_guest, sync_person_from_guest

pytestmark = pytest.mark.django_db


def _person(guest: Guest) -> Person:
    return Person.objects.get(legacy_id=f"guest-{guest.pk}")


def test_creating_a_guest_mirrors_a_person_with_channels() -> None:
    guest = cast(
        Guest,
        GuestFactory(
            title="Dr",
            first_name="Ada",
            last_name="Lovelace",
            contact_method=ContactMethod.EMAIL,
            marketing_consent=True,
        ),
    )

    person = _person(guest)
    assert person.first_name == "Ada"
    assert person.last_name == "Lovelace"
    assert person.title == "Dr"
    assert person.country_id == guest.country_id
    assert person.marketing_consent is True
    assert person.status == "active"
    assert person.preferred_method == "email"
    assert person.user_id is None
    # GAP-045 D2: a Guest mirror is always a CUSTOMER for the /contacts directory.
    assert person.kind == "customer"

    email = PersonEmail.objects.get(contact=person)
    assert email.email == guest.email
    assert email.is_primary is True and email.label == "primary"
    phone = PersonPhone.objects.get(contact=person)
    assert phone.number == guest.phone
    assert phone.is_primary is True and phone.label == "mobile"


def test_updating_guest_fields_updates_the_person() -> None:
    guest = cast(Guest, GuestFactory(first_name="Ada"))
    guest.first_name = "Augusta"
    guest.last_name = "King"
    guest.save()

    person = _person(guest)
    assert person.first_name == "Augusta"
    assert person.last_name == "King"


def test_changing_email_reconciles_the_primary_in_place() -> None:
    guest = cast(Guest, GuestFactory())
    original_pk = PersonEmail.objects.get(contact=_person(guest)).pk

    guest.email = "augusta@example.com"
    guest.save()

    person = _person(guest)
    emails = PersonEmail.objects.filter(contact=person)
    # Exactly one primary email, updated in place — no duplicate, no
    # one_primary_email_per_contact violation.
    assert emails.count() == 1
    email = emails.get()
    assert email.pk == original_pk
    assert email.email == "augusta@example.com"
    assert email.is_primary is True


def test_anonymizing_a_guest_scrubs_the_person_mirror_audit_trail() -> None:
    """GDPR erasure: the per-save mirror writes the guest's real PII onto the
    audit-tracked Person, so anonymizing the guest must scrub the Person's trail
    too — not just copy the redacted values across."""
    from django.contrib.contenttypes.models import ContentType

    from core.models import AuditLog

    guest = cast(Guest, GuestFactory())
    person = _person(guest)
    guest.last_name = "Sensitive"
    guest.save(update_fields=["last_name"])

    ct = ContentType.objects.get_for_model(Person)
    pre = AuditLog.objects.filter(content_type=ct, object_id=str(person.pk))
    assert any("Sensitive" in str(r.field_diffs) for r in pre)  # sanity: it leaked

    guest.anonymize()

    rows = list(AuditLog.objects.filter(content_type=ct, object_id=str(person.pk)))
    for r in rows:
        assert "Sensitive" not in str(r.field_diffs), f"leaked in {r.field_diffs}"
    person.refresh_from_db()
    assert person.status == "anonymized"
    assert person.last_name == "[REDACTED]"


def test_save_touching_no_synced_field_skips_the_mirror() -> None:
    guest = cast(Guest, GuestFactory())
    person = _person(guest)
    # A manual edit the sync would clobber if it ran.
    person.first_name = "MANUAL"
    person.save(update_fields=["first_name", "updated_at"])

    guest.save(update_fields=["updated_at"])

    person.refresh_from_db()
    assert person.first_name == "MANUAL"


def test_clearing_email_removes_the_primary() -> None:
    # Keep the phone so the ACTIVE-contactable CHECK still holds.
    guest = cast(Guest, GuestFactory())
    assert PersonEmail.objects.filter(contact=_person(guest)).exists()

    guest.email = None
    guest.save()

    assert not PersonEmail.objects.filter(contact=_person(guest)).exists()


def test_changing_phone_reconciles_the_primary_in_place() -> None:
    guest = cast(Guest, GuestFactory())
    original_pk = PersonPhone.objects.get(contact=_person(guest)).pk

    guest.phone = "+441234567890"
    guest.save()

    phones = PersonPhone.objects.filter(contact=_person(guest))
    assert phones.count() == 1
    phone = phones.get()
    assert phone.pk == original_pk
    assert phone.number == "+441234567890"


def test_clearing_phone_removes_the_primary() -> None:
    # Keep the email so the ACTIVE-contactable CHECK still holds.
    guest = cast(Guest, GuestFactory())
    assert PersonPhone.objects.filter(contact=_person(guest)).exists()

    guest.phone = ""
    guest.save()

    assert not PersonPhone.objects.filter(contact=_person(guest)).exists()


@pytest.mark.parametrize(
    ("guest_status", "expected"),
    [
        (GuestStatus.ACTIVE, "active"),
        (GuestStatus.ARCHIVED, "inactive"),
        (GuestStatus.ANONYMIZED, "anonymized"),
    ],
)
def test_status_mapping(guest_status: GuestStatus, expected: str) -> None:
    guest = cast(Guest, GuestFactory(status=guest_status))
    assert _person(guest).status == expected


def test_preferred_method_defaults_to_email_when_guest_has_no_preference() -> None:
    guest = cast(Guest, GuestFactory(contact_method=None))
    assert _person(guest).preferred_method == "email"


def test_sync_is_idempotent_and_updates_an_existing_3b_person() -> None:
    guest = cast(Guest, GuestFactory(first_name="Ada"))

    # Simulate a second pass (e.g. the 3b migration had already created it).
    sync_person_from_guest(guest)
    sync_person_from_guest(guest)

    assert Person.objects.filter(legacy_id=f"guest-{guest.pk}").count() == 1
    person = _person(guest)
    assert PersonEmail.objects.filter(contact=person).count() == 1
    assert PersonPhone.objects.filter(contact=person).count() == 1


def test_person_for_guest_recreates_a_missing_mirror() -> None:
    guest = cast(Guest, GuestFactory())
    Person.objects.filter(legacy_id=f"guest-{guest.pk}").delete()

    person = person_for_guest(guest)
    assert person.legacy_id == f"guest-{guest.pk}"
    assert Person.objects.filter(legacy_id=f"guest-{guest.pk}").count() == 1
