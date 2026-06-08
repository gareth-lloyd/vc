"""GuestLoader / EnquiryLoader transform behaviour (honest-integrity import)."""

from __future__ import annotations

from data_migration.loaders.reservations import EnquiryLoader, GuestLoader
from reservations.enums import GuestStatus


def _guest_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": 1,
        "FirstName": "Ada",
        "LastName": "Lovelace",
        "Email": "",
        "MobileNo": "",
    }
    base.update(overrides)
    return base


def test_guest_phone_only_imports_with_null_email() -> None:
    """A phone-only legacy client is now a valid Guest (was dropped before)."""
    kwargs = GuestLoader().transform(_guest_row(MobileNo="+44 7911 123456"))
    assert kwargs is not None
    assert kwargs["email"] is None
    assert kwargs["phone"] == "+447911123456"
    assert kwargs["status"] == GuestStatus.ACTIVE


def test_guest_email_only_is_active_and_lowercased() -> None:
    kwargs = GuestLoader().transform(_guest_row(Email="ADA@Example.com"))
    assert kwargs is not None
    assert kwargs["email"] == "ada@example.com"
    assert kwargs["status"] == GuestStatus.ACTIVE


def test_guest_channelless_is_dispositioned_archived() -> None:
    """No email and no phone → ARCHIVED (exempt from the contactability CHECK)."""
    kwargs = GuestLoader().transform(_guest_row(Email="", MobileNo=""))
    assert kwargs is not None
    assert kwargs["email"] is None
    assert kwargs["phone"] == ""
    assert kwargs["status"] == GuestStatus.ARCHIVED


def test_guest_email_without_at_becomes_null() -> None:
    kwargs = GuestLoader().transform(_guest_row(Email="not-an-email", MobileNo="+44 7911 123456"))
    assert kwargs is not None
    assert kwargs["email"] is None


def test_guest_with_no_name_is_skipped() -> None:
    assert GuestLoader().transform(_guest_row(FirstName="", LastName="")) is None


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
