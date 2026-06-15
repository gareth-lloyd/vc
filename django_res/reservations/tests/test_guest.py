"""Tests for the `Guest` model — anonymize() and merge()."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from core.models import AuditLog
from pricing.models import Currency
from properties.models import Property
from reservations.enums import ContactMethod, GuestStatus, PaymentMethod
from reservations.models import (
    Booking,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)


def _make_booking(
    *,
    guest: Guest,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> Booking:
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        children=0,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
    )


@pytest.mark.django_db
def test_anonymize_redacts_pii_and_preserves_fks(
    guest: Guest,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    booking = _make_booking(guest=guest, property_=property_, gbp=gbp, terms=terms)

    guest.anonymize()

    guest.refresh_from_db()
    booking.refresh_from_db()
    assert guest.status == GuestStatus.ANONYMIZED.value
    assert guest.first_name == "[REDACTED]"
    assert guest.last_name == "[REDACTED]"
    # No synthetic email — absence is NULL (the row is marked by status).
    assert guest.email is None
    assert guest.phone == ""
    assert guest.contact_method is None
    assert guest.marketing_consent is False
    assert guest.anonymized_at is not None
    # FK survives — booking still points at the anonymized guest.
    assert booking.guest_id == guest.pk


@pytest.mark.django_db
def test_merge_rewrites_fks_and_hard_deletes_source(
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    keep = Guest.objects.create(first_name="Keep", last_name="Me", email="keep@x.com")
    duplicate = Guest.objects.create(first_name="Dup", last_name="Me", email="dup@x.com")
    booking = _make_booking(guest=duplicate, property_=property_, gbp=gbp, terms=terms)

    duplicate.merge(keep)

    assert not Guest.objects.filter(pk=duplicate.pk).exists()
    booking.refresh_from_db()
    assert booking.guest_id == keep.pk


@pytest.mark.django_db
def test_merge_into_self_raises(guest: Guest) -> None:
    with pytest.raises(ValueError):
        guest.merge(guest)


@pytest.mark.django_db
def test_anonymize_scrubs_pii_from_audit_log(guest: Guest) -> None:
    """GDPR erasure: after anonymize, no AuditLog row for the guest may
    retain cleartext PII — including the anonymize-save row itself (BUG-012)."""
    from core.audit import REDACTED

    old_email = "leaky@example.com"
    guest.email = old_email
    guest.last_name = "Sensitive"
    guest.save(update_fields=["email", "last_name"])

    ct = ContentType.objects.get_for_model(Guest)
    pre_rows = AuditLog.objects.filter(content_type=ct, object_id=str(guest.pk))
    # Sanity: the pre-scrub trail leaked the cleartext.
    assert any(old_email in str(r.field_diffs) for r in pre_rows)

    guest.anonymize()

    rows = list(AuditLog.objects.filter(content_type=ct, object_id=str(guest.pk)))
    for r in rows:
        blob = str(r.field_diffs)
        assert old_email not in blob, f"leaked email in {r.field_diffs}"
        assert "Sensitive" not in blob, f"leaked last_name in {r.field_diffs}"
    # The anonymize-save row survives structurally, values tombstoned.
    pii_rows = [r for r in rows if "email" in r.field_diffs]
    assert pii_rows
    for r in pii_rows:
        for side in r.field_diffs["email"]:
            assert side in (None, REDACTED)


@pytest.mark.django_db
def test_merge_scrubs_deletion_row_pii_but_keeps_structure(
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """The hard-delete row from merge() must keep who/when/__deleted__ but
    redact the PII values (BUG-012)."""
    from core.audit import REDACTED

    keep = Guest.objects.create(first_name="Keep", last_name="Me", email="keep@x.com")
    duplicate = Guest.objects.create(first_name="Dup", last_name="Leaky", email="dup@x.com")

    duplicate.merge(keep)

    ct = ContentType.objects.get_for_model(Guest)
    rows = list(AuditLog.objects.filter(content_type=ct, object_id=str(duplicate.pk)))
    deletion_rows = [r for r in rows if r.field_diffs.get("__deleted__")]
    assert deletion_rows, "expected a deletion audit row"
    for r in deletion_rows:
        blob = str(r.field_diffs)
        assert "Leaky" not in blob
        assert "dup@x.com" not in blob
        # Structure preserved: the tombstone marker and field keys survive.
        assert r.field_diffs["__deleted__"] is True
        assert r.field_diffs["last_name"][0] == REDACTED
        # Non-PII fields untouched.
        assert r.field_diffs["status"][0] == GuestStatus.ACTIVE.value


@pytest.mark.django_db
def test_changing_contact_method_writes_audit_row(guest: Guest) -> None:
    """The preferred-channel change must be captured in the AuditLog trail,
    not just registered in the audit registry."""
    # The fixture guest has an email but no phone, so EMAIL is the
    # contactability-valid preference to switch to.
    guest.contact_method = ContactMethod.EMAIL.value
    guest.save(update_fields=["contact_method"])

    ct = ContentType.objects.get_for_model(Guest)
    rows = AuditLog.objects.filter(content_type=ct, object_id=str(guest.pk))
    matching = [r for r in rows if "contact_method" in r.field_diffs]
    assert matching, "expected an AuditLog row capturing the contact_method change"
    assert matching[-1].field_diffs["contact_method"][1] == ContactMethod.EMAIL.value
