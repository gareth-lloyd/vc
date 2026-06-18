"""Integration: Enquiry + Quotation transitions land AuditLog rows (FG-014).

Also pins that the Enquiry's denormalised PII is recorded as the `[REDACTED]`
sentinel (registered `sensitive=`) rather than cleartext — the Enquiry has no
`anonymize()`/`scrub_pii` erasure path, so the sentinel is the only guard.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from core.audit import REDACTED
from core.models import AuditLog
from reservations.enums import EnquiryStatus, QuotationStatus
from reservations.models import Booking, BookingGuest, Enquiry, Guest, Quotation
from reservations.models.terms import TermsVersion


@pytest.mark.django_db
def test_enquiry_status_transition_writes_audit_row() -> None:
    enquiry = Enquiry.objects.create(status=EnquiryStatus.NEW.value)

    enquiry.contact()

    ct = ContentType.objects.get_for_model(Enquiry)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(enquiry.pk))
    status_rows = [r for r in rows if "status" in r.field_diffs]
    assert status_rows, "expected an AuditLog row capturing the enquiry status change"
    assert status_rows[-1].field_diffs["status"] == [
        EnquiryStatus.NEW.value,
        EnquiryStatus.CONTACTED.value,
    ]


@pytest.mark.django_db
def test_enquiry_pii_recorded_as_redacted_sentinel() -> None:
    """Editing an enquiry's PII must not write cleartext to the trail."""
    enquiry = Enquiry.objects.create(status=EnquiryStatus.NEW.value)

    enquiry.first_name = "Grace"
    enquiry.last_name = "Hopper"
    enquiry.email = "grace@example.com"
    enquiry.phone = "+15551234567"
    enquiry.save(update_fields=["first_name", "last_name", "email", "phone"])

    ct = ContentType.objects.get_for_model(Enquiry)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(enquiry.pk))
    blob = " ".join(str(r.field_diffs) for r in rows)
    assert "Grace" not in blob
    assert "grace@example.com" not in blob
    assert "+15551234567" not in blob

    pii_row = next(r for r in rows if "email" in r.field_diffs)
    assert pii_row.field_diffs["email"] == ["", REDACTED]
    assert pii_row.field_diffs["first_name"] == ["", REDACTED]


@pytest.mark.django_db
def test_quotation_status_transition_writes_audit_row(guest: Guest) -> None:
    terms = TermsVersion.objects.create(
        version="2026-09",
        body_markdown="**T&Cs**",
        published_at=timezone.now(),
        is_current=True,
    )
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
        status=QuotationStatus.SENT.value,
    )

    quotation.cancel(reason="guest withdrew")

    ct = ContentType.objects.get_for_model(Quotation)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(quotation.pk))
    status_rows = [r for r in rows if "status" in r.field_diffs]
    assert status_rows, "expected an AuditLog row capturing the quotation status change"
    assert status_rows[-1].field_diffs["status"] == [
        QuotationStatus.SENT.value,
        QuotationStatus.CANCELLED.value,
    ]


# ---------------------------------------------------------------------------
# GAP-045 Unit 3c-3a — person_id is audit-tracked alongside guest_id
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_enquiry_person_reassignment_writes_audit_row() -> None:
    """Repointing an Enquiry's unified Person FK (a real .save() path, e.g. the
    write serializer) lands an AuditLog row capturing the person_id change."""
    from accounts.models import Person

    enquiry = Enquiry.objects.create(status=EnquiryStatus.NEW.value)
    person = Person.objects.create(first_name="Grace", last_name="Hopper")

    enquiry.person = person
    enquiry.save(update_fields=["person"])

    ct = ContentType.objects.get_for_model(Enquiry)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(enquiry.pk))
    person_rows = [r for r in rows if "person_id" in r.field_diffs]
    assert person_rows, "expected an AuditLog row capturing the enquiry person_id change"
    assert person_rows[-1].field_diffs["person_id"] == [None, person.pk]


@pytest.mark.django_db
def test_quotation_person_reassignment_writes_audit_row(guest: Guest) -> None:
    """Repointing a Quotation's Person FK lands an AuditLog row (person_id)."""
    from accounts.models import Person

    terms = TermsVersion.objects.create(
        version="2026-10", body_markdown="x", published_at=timezone.now()
    )
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    person = Person.objects.create(first_name="Grace", last_name="Hopper")

    quotation.person = person
    quotation.save(update_fields=["person"])

    ct = ContentType.objects.get_for_model(Quotation)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(quotation.pk))
    person_rows = [r for r in rows if "person_id" in r.field_diffs]
    assert person_rows, "expected an AuditLog row capturing the quotation person_id change"
    assert person_rows[-1].field_diffs["person_id"] == [None, person.pk]


@pytest.mark.django_db
def test_booking_birth_audits_guest_and_person(
    guest: Guest, gbp: object, terms: TermsVersion, property_: object
) -> None:
    """Booking now tracks guest_id + person_id (a pre-existing audit gap). The
    customer it was born with is captured in the creation diff; post-create LEAD
    reassignment is audited on BookingGuest (it mutates Booking only via a
    signal .update(), which bypasses the trail by design). The creation row is
    keyed to object_id="" — pre_save fires before the INSERT assigns the pk."""
    from datetime import date

    from reservations.factories import make_occupying_booking

    booking = make_occupying_booking(
        property=property_,  # type: ignore[arg-type]
        guest=guest,
        currency=gbp,  # type: ignore[arg-type]
        terms=terms,
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 8),
    )

    ct = ContentType.objects.get_for_model(Booking)
    birth = [
        r
        for r in AuditLog.objects.filter(content_type=ct, object_id="")
        if "guest_id" in r.field_diffs and "person_id" in r.field_diffs
    ]
    assert birth, "expected the Booking creation diff to capture guest_id + person_id"
    assert birth[-1].field_diffs["guest_id"] == [None, guest.pk]
    assert birth[-1].field_diffs["person_id"] == [None, booking.person_id]
    assert booking.person_id is not None


@pytest.mark.django_db
def test_booking_guest_birth_audits_person(
    guest: Guest, gbp: object, terms: TermsVersion, property_: object
) -> None:
    """The LEAD BookingGuest row also tracks person_id alongside guest_id."""
    from datetime import date

    from reservations.factories import make_occupying_booking

    booking = make_occupying_booking(
        property=property_,  # type: ignore[arg-type]
        guest=guest,
        currency=gbp,  # type: ignore[arg-type]
        terms=terms,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 8),
    )
    lead = BookingGuest.objects.get(booking=booking)

    ct = ContentType.objects.get_for_model(BookingGuest)
    birth = [
        r
        for r in AuditLog.objects.filter(content_type=ct, object_id="")
        if "person_id" in r.field_diffs
    ]
    assert birth, "expected the BookingGuest creation diff to capture person_id"
    assert birth[-1].field_diffs["person_id"] == [None, lead.person_id]
    assert lead.person_id is not None
