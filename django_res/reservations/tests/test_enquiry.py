"""Tests for the Enquiry state machine + EnquiryNote → EnquiryEvent signal."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from core.exceptions import InvalidTransition
from reservations.enums import (
    EnquiryEventKind,
    EnquiryNoteKind,
    EnquiryStatus,
)
from reservations.models import (
    Enquiry,
    EnquiryEvent,
    EnquiryNote,
    Guest,
    Quotation,
    TermsVersion,
)

if TYPE_CHECKING:
    from pricing.models import Currency


@pytest.fixture
def enquiry(db: None, guest: Guest) -> Enquiry:
    return Enquiry.objects.create(guest=guest, email="ada@example.com")


@pytest.fixture
def quotation(db: None, guest: Guest, gbp: Currency, terms: TermsVersion) -> Quotation:
    return Quotation.objects.create(
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )


@pytest.mark.django_db
def test_contact_new_to_contacted_writes_event(enquiry: Enquiry) -> None:
    enquiry.contact()
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.CONTACTED.value
    event = EnquiryEvent.objects.get(enquiry=enquiry, kind=EnquiryEventKind.CONTACTED.value)
    assert event.from_status == EnquiryStatus.NEW.value
    assert event.to_status == EnquiryStatus.CONTACTED.value


@pytest.mark.django_db
def test_contact_from_wrong_state_raises(enquiry: Enquiry) -> None:
    enquiry.contact()
    with pytest.raises(InvalidTransition):
        enquiry.contact()


@pytest.mark.django_db
def test_quote_sent_writes_event_with_quotation_id(enquiry: Enquiry, quotation: Quotation) -> None:
    enquiry.quote_sent(quotation)
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.QUOTED.value
    event = EnquiryEvent.objects.get(enquiry=enquiry, kind=EnquiryEventKind.QUOTE_SENT.value)
    assert event.meta == {"quotation_id": quotation.pk}


@pytest.mark.django_db
def test_quote_sent_from_lost_raises(enquiry: Enquiry, quotation: Quotation) -> None:
    enquiry.lose("dropped")
    with pytest.raises(InvalidTransition):
        enquiry.quote_sent(quotation)


@pytest.mark.django_db
def test_assign_writes_assigned_event(enquiry: Enquiry) -> None:
    from accounts.models import User

    user = User.objects.create_user(email="ops@example.com", password="x")
    enquiry.assign(user)
    enquiry.refresh_from_db()
    assert enquiry.assigned_to_id == user.pk
    event = EnquiryEvent.objects.get(enquiry=enquiry, kind=EnquiryEventKind.ASSIGNED.value)
    assert event.meta["assignee_to"] == user.pk
    assert event.from_status == event.to_status  # non-transition


@pytest.mark.django_db
def test_convert_from_quoted(enquiry: Enquiry, quotation: Quotation) -> None:
    enquiry.quote_sent(quotation)
    enquiry.convert(quotation)
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.CONVERTED.value


@pytest.mark.django_db
def test_convert_from_new_raises(enquiry: Enquiry, quotation: Quotation) -> None:
    with pytest.raises(InvalidTransition):
        enquiry.convert(quotation)


@pytest.mark.django_db
def test_lose_writes_lost_event(enquiry: Enquiry) -> None:
    enquiry.lose("client went elsewhere")
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.LOST.value
    event = EnquiryEvent.objects.get(enquiry=enquiry, kind=EnquiryEventKind.LOST.value)
    assert event.reason == "client went elsewhere"


@pytest.mark.django_db
def test_lose_from_converted_raises(enquiry: Enquiry, quotation: Quotation) -> None:
    enquiry.quote_sent(quotation)
    enquiry.convert(quotation)
    with pytest.raises(InvalidTransition):
        enquiry.lose()


@pytest.mark.django_db
def test_reopen_from_lost(enquiry: Enquiry) -> None:
    enquiry.lose()
    enquiry.reopen()
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.NEW.value


@pytest.mark.django_db
def test_reopen_from_new_raises(enquiry: Enquiry) -> None:
    with pytest.raises(InvalidTransition):
        enquiry.reopen()


@pytest.mark.django_db
def test_enquiry_note_post_save_emits_note_added_event(enquiry: Enquiry) -> None:
    EnquiryNote.objects.create(enquiry=enquiry, kind=EnquiryNoteKind.GENERAL.value, body="hi")
    event = EnquiryEvent.objects.get(enquiry=enquiry, kind=EnquiryEventKind.NOTE_ADDED.value)
    assert event.from_status == event.to_status == EnquiryStatus.NEW.value


@pytest.mark.django_db
def test_reference_auto_generated(enquiry: Enquiry) -> None:
    assert enquiry.reference.startswith("E-")
