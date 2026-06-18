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
from reservations.models import Enquiry, Guest, Quotation
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
        EnquiryStatus.PROGRESSING.value,
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
