"""GAP-112: classify a customer-less legacy enquiry against the people the
sheet imports minted after it loaded."""

from __future__ import annotations

from typing import cast

import pytest

from accounts.enums import PersonKind, PersonStatus
from accounts.models import Person, PersonEmail
from data_migration.relink import classify_enquiry
from reservations.factories import EnquiryFactory
from reservations.models import Enquiry

pytestmark = pytest.mark.django_db


def _person(first: str, last: str, email: str, **kwargs: object) -> Person:
    person = Person.objects.create(first_name=first, last_name=last, **kwargs)
    PersonEmail.objects.create(contact=person, email=email, is_primary=True)
    return person


def _enquiry(first: str = "Ada", last: str = "Lovelace", email: str = "ada@example.com") -> Enquiry:
    return cast(
        Enquiry,
        EnquiryFactory(
            person=None, first_name=first, last_name=last, email=email, legacy_id="enquiry-1"
        ),
    )


def test_a_single_owner_with_agreeing_names_relinks() -> None:
    ada = _person("Ada", "Lovelace", "ada@example.com")

    assert classify_enquiry(_enquiry(email="ADA@example.com")) == ("relinked", ada)


def test_no_email_is_reported() -> None:
    _person("Ada", "Lovelace", "ada@example.com")

    assert classify_enquiry(_enquiry(email="")) == ("no_email", None)


def test_an_address_without_an_at_sign_counts_as_no_email() -> None:
    assert classify_enquiry(_enquiry(email="not given")) == ("no_email", None)


def test_an_address_nobody_holds_is_unmatched() -> None:
    _person("Ada", "Lovelace", "ada@example.com")

    assert classify_enquiry(_enquiry(email="someone@example.com")) == ("unmatched", None)


def test_an_address_held_by_two_people_is_shared_even_if_one_is_a_contact() -> None:
    # The matcher would pick the customer (BUG-030 §18); the relink pass does
    # not guess — any second holder makes the address ambiguous.
    _person("Ada", "Lovelace", "ada@example.com", kind=PersonKind.CUSTOMER)
    _person("Ada", "Lovelace", "ada@example.com", kind=PersonKind.CONTACT)

    assert classify_enquiry(_enquiry()) == ("shared_email", None)


def test_an_address_shared_with_an_inactive_person_is_still_shared() -> None:
    _person("Ada", "Lovelace", "ada@example.com")
    _person("Charles", "Babbage", "ada@example.com", status=PersonStatus.INACTIVE)

    assert classify_enquiry(_enquiry()) == ("shared_email", None)


def test_a_single_owner_with_a_different_last_name_is_names_disagree() -> None:
    _person("Ada", "Byron", "ada@example.com")

    assert classify_enquiry(_enquiry()) == ("names_disagree", None)


def test_a_single_inactive_owner_is_reported_as_inactive() -> None:
    _person("Ada", "Lovelace", "ada@example.com", status=PersonStatus.INACTIVE)

    assert classify_enquiry(_enquiry()) == ("inactive", None)


def test_the_anon_placeholder_counts_as_no_first_name() -> None:
    # EnquiryLoader matches first, then stores "(anon)" for a nameless row.
    ada = _person("Ada", "Lovelace", "ada@example.com")

    assert classify_enquiry(_enquiry(first="(anon)", last="")) == ("relinked", ada)


def test_a_real_first_name_of_anon_with_a_last_name_is_kept() -> None:
    _person("Ada", "Lovelace", "ada@example.com")

    assert classify_enquiry(_enquiry(first="(anon)", last="Lovelace")) == ("names_disagree", None)
