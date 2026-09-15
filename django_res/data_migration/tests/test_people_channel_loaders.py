"""UserLoader, ContactEmailLoader and ContactPhoneLoader transforms (BUG-030
§17 phone normalisation + the test-coverage sweep)."""

from __future__ import annotations

import pytest

from accounts.enums import EmailLabel
from accounts.models import Person, PersonEmail, PersonPhone
from core.enums import StaffRole
from data_migration.loaders.people import ContactEmailLoader, ContactPhoneLoader, UserLoader

pytestmark = pytest.mark.django_db


@pytest.fixture
def contact() -> Person:
    return Person.objects.create(first_name="Ada", last_name="Lovelace", legacy_id="70")


def _phone_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Id": 1,
        "ContactId": 70,
        "CountryCode": "",
        "MobileNo": "",
        "IsPrimary": 1,
    }
    row.update(overrides)
    return row


# --- ContactPhoneLoader (BUG-030 §17) ---


@pytest.mark.parametrize(
    ("country_code", "number", "expected"),
    [
        ("0044", "7770302297", "+447770302297"),
        ("44", "07771950930", "+447771950930"),
        ("+30", "6944123456", "+306944123456"),
        ("", "07919591288", "+447919591288"),  # no calling code: GB default
        (None, "07919591288", "+447919591288"),
    ],
)
def test_contact_phone_is_e164_anchored_on_the_calling_code(
    contact: Person, country_code: str | None, number: str, expected: str
) -> None:
    kwargs = ContactPhoneLoader().transform(_phone_row(CountryCode=country_code, MobileNo=number))
    assert kwargs is not None
    assert kwargs["number"] == expected


@pytest.mark.parametrize("country_code", ["0", "00", "UK", "+"])
def test_contact_phone_unreadable_calling_code_falls_back_to_gb(
    contact: Person, country_code: str
) -> None:
    kwargs = ContactPhoneLoader().transform(
        _phone_row(CountryCode=country_code, MobileNo="07771950930")
    )
    assert kwargs is not None
    assert kwargs["number"] == "+447771950930"


def test_contact_phone_invalid_number_keeps_its_calling_code(contact: Person) -> None:
    kwargs = ContactPhoneLoader().transform(_phone_row(CountryCode="0030", MobileNo="12345"))
    assert kwargs is not None
    assert kwargs["number"] == "+30 12345"


def test_contact_phone_unparseable_number_without_a_code_is_kept_raw(contact: Person) -> None:
    kwargs = ContactPhoneLoader().transform(_phone_row(MobileNo=" call office "))
    assert kwargs is not None
    assert kwargs["number"] == "call office"


def test_contact_phone_blank_number_or_unknown_contact_is_skipped(contact: Person) -> None:
    assert ContactPhoneLoader().transform(_phone_row(MobileNo="  ")) is None
    assert ContactPhoneLoader().transform(_phone_row(ContactId=999, MobileNo="07919591288")) is None


def test_contact_phone_second_primary_is_demoted(contact: Person) -> None:
    PersonPhone.objects.create(contact=contact, number="+447919591288", is_primary=True)
    kwargs = ContactPhoneLoader().transform(_phone_row(MobileNo="07771950930"))
    assert kwargs is not None
    assert kwargs["is_primary"] is False


# --- ContactEmailLoader ---


def test_contact_email_is_lowercased_and_primary(contact: Person) -> None:
    kwargs = ContactEmailLoader().transform(
        {"Id": 1, "ContactId": 70, "Email": " Ada@Example.COM ", "IsPrimary": 1}
    )
    assert kwargs == {
        "contact": contact,
        "email": "ada@example.com",
        "is_primary": True,
        "label": EmailLabel.PRIMARY,
    }


def test_contact_email_second_primary_is_demoted_to_other(contact: Person) -> None:
    PersonEmail.objects.create(contact=contact, email="first@example.com", is_primary=True)
    kwargs = ContactEmailLoader().transform(
        {"Id": 2, "ContactId": 70, "Email": "second@example.com", "IsPrimary": 1}
    )
    assert kwargs is not None
    assert (kwargs["is_primary"], kwargs["label"]) == (False, EmailLabel.OTHER)


def test_contact_email_without_at_or_contact_is_skipped(contact: Person) -> None:
    loader = ContactEmailLoader()
    assert loader.transform({"Id": 1, "ContactId": 70, "Email": "nope", "IsPrimary": 1}) is None
    assert loader.transform({"Id": 1, "ContactId": 999, "Email": "a@b.com", "IsPrimary": 1}) is None


# --- UserLoader ---


@pytest.mark.parametrize(("admin", "role"), [(1, StaffRole.ADMIN), (0, StaffRole.RESERVATIONS)])
def test_user_transform_maps_role_and_normalises_email(admin: int, role: StaffRole) -> None:
    kwargs = UserLoader().transform(
        {
            "Id": 1,
            "Email": " Staff@VillaCollective.com ",
            "FirstName": " Sam ",
            "LastName": "Reyes",
            "IsSystemAdmin": admin,
            "IsActive": 1,
            "MobileNo": None,
            "LoginAt": None,
            "LoginIP": "",
        }
    )
    assert kwargs is not None
    assert kwargs["email"] == "staff@villacollective.com"
    assert kwargs["first_name"] == "Sam"
    assert kwargs["role"] == role
    assert kwargs["is_staff"] is True
    assert kwargs["last_login_ip"] is None


def test_user_without_a_valid_email_is_skipped() -> None:
    assert UserLoader().transform({"Id": 1, "Email": "staff"}) is None
