"""GAP-094 — the `booking.contract` email carries the generated PDF.

`reservations` cannot import `comms` (upward edge on the import spine), so
delivery is a receiver on `booking_document_send_requested`. It has to survive
three things the confirmation email never faced: a guest with no address, a
second send against the *same* document (which `EmailService.send` would dedupe
into a silent no-op), and a comms outage that must leave `sent_to_guest_at`
null rather than lying about delivery.
"""

from __future__ import annotations

from datetime import date
from typing import cast

import pytest
import structlog
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.test import override_settings
from django.utils import timezone

from accounts.factories import CustomerPersonFactory
from accounts.models import Person
from comms.enums import EmailLogStatus
from comms.management.commands.seed_email_templates import sync_templates
from comms.models import EmailLog, EmailTemplate, SmtpProfile
from comms.signals import booking_document_send_requested_handler
from pricing.models import Currency
from properties.models import Property
from reservations.factories import make_occupying_booking
from reservations.models import BookingDocument, TermsVersion

PDF_BYTES = b"%PDF-1.7\ncontract\n"


@pytest.fixture
def gbp(db: None) -> Currency:
    return Currency.objects.create(code="GBP", name="Pound sterling", symbol="£")


@pytest.fixture
def customer(db: None) -> Person:
    return cast(
        Person,
        CustomerPersonFactory(
            first_name="Ada", last_name="Lovelace", primary_email="ada@example.com"
        ),
    )


@pytest.fixture
def emailless_customer(db: None) -> Person:
    # Empty string (not None) is factory-boy's "suppress this channel" signal.
    return cast(Person, CustomerPersonFactory(first_name="Nemo", primary_email=""))


@pytest.fixture
def terms(db: None) -> TermsVersion:
    return TermsVersion.objects.create(
        version="2026-01",
        body_markdown="**T&Cs**",
        published_at=timezone.now(),
        is_current=True,
    )


@pytest.fixture
def property_(db: None) -> Property:
    from properties.models import Country, Region

    country, _ = Country.objects.get_or_create(
        iso2="GB", defaults={"name": "United Kingdom", "iso3": "GBR"}
    )
    region = Region.objects.create(country=country, name="South West", slug="south-west")
    return Property.objects.create(
        name="Test Villa",
        display_name="Test Villa",
        slug="test-villa",
        region=region,
    )


def _make_document(
    *,
    property_: Property,
    person: Person,
    gbp: Currency,
    terms: TermsVersion,
    date_from: date = date(2026, 6, 10),
) -> BookingDocument:
    """A committed contract row with a real file, without rendering a PDF.

    The render seam has its own tests (`test_booking_contract_render.py`);
    what matters here is the metadata the send leg reads off the row.
    """
    booking = make_occupying_booking(
        property=property_,
        person=person,
        currency=gbp,
        terms=terms,
        date_from=date_from,
        date_to=date(date_from.year, date_from.month, date_from.day + 7),
    )
    document = BookingDocument.objects.create(booking=booking, kind="contract")
    document.file.save(f"{booking.reference}-contract-{document.pk}.pdf", ContentFile(PDF_BYTES))
    return document


def _fire(document: BookingDocument, actor: object | None = None) -> None:
    booking_document_send_requested_handler(sender=BookingDocument, document=document, actor=actor)


# ----------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_send_attaches_the_document_and_stamps_the_row(
    run_on_commit_immediately: None,
    system_profile: SmtpProfile,
    property_: Property,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """Dispatch runs inline here, which is what staging actually does.

    `CELERY_TASK_ALWAYS_EAGER` plus autocommit means `transaction.on_commit`
    fires immediately, so `EmailService.send` returns a row that is already
    SENT — never QUEUED. Asserting the whole way to `mail.outbox` is what
    keeps the stamp condition honest.
    """
    sync_templates()
    document = _make_document(property_=property_, person=customer, gbp=gbp, terms=terms)
    mail.outbox.clear()

    _fire(document)

    log = EmailLog.objects.get(template_key="booking.contract")
    assert log.to == ["ada@example.com"]
    assert log.status == EmailLogStatus.SENT
    assert log.correlation["booking_id"] == document.booking_id
    assert log.correlation["document_id"] == document.pk
    filename = f"{document.booking.reference}-contract-{document.pk}.pdf"
    assert log.attachments == [
        {
            "filename": filename,
            "content_type": "application/pdf",
            "size": len(PDF_BYTES),
            "storage_key": document.file.name,
            "storage": "documents",
        }
    ]
    # The PDF really reaches the wire, not just the metadata row.
    assert mail.outbox[0].attachments == [(filename, PDF_BYTES, "application/pdf")]
    document.refresh_from_db()
    assert document.sent_to_guest_at is not None


@pytest.mark.django_db
def test_deferred_dispatch_also_stamps(
    system_profile: SmtpProfile,
    property_: Property,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """The other half of the stamp condition: no `run_on_commit_immediately`,
    so the row is still QUEUED when the receiver reads it back. Both states
    mean "handed to the mail pipeline" and both must stamp — only a refusal
    (BLOCKED) or a terminal failure must not."""
    sync_templates()
    document = _make_document(property_=property_, person=customer, gbp=gbp, terms=terms)

    _fire(document)

    assert EmailLog.objects.get(template_key="booking.contract").status == EmailLogStatus.QUEUED
    document.refresh_from_db()
    assert document.sent_to_guest_at is not None


@pytest.mark.django_db
def test_body_names_the_property_and_reference(
    system_profile: SmtpProfile,
    property_: Property,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    sync_templates()
    document = _make_document(property_=property_, person=customer, gbp=gbp, terms=terms)

    _fire(document)

    log = EmailLog.objects.get(template_key="booking.contract")
    assert "Test Villa" in log.rendered_subject
    assert document.booking.reference in log.rendered_body_html
    assert "Ada" in log.rendered_body_html


# ----------------------------------------------------------------------
# Resend semantics
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_second_send_on_the_same_document_mints_a_second_row(
    system_profile: SmtpProfile,
    property_: Property,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """`EmailService.send` dedupes on (template_key, to, correlation), so a
    staff resend would otherwise return the original row and send nothing."""
    sync_templates()
    document = _make_document(property_=property_, person=customer, gbp=gbp, terms=terms)

    _fire(document)
    _fire(document)

    logs = list(EmailLog.objects.filter(template_key="booking.contract").order_by("queued_at"))
    assert len(logs) == 2
    assert logs[1].correlation["resent_from"] == logs[0].pk
    # The resend carries the same attachment metadata, so the guest gets the
    # same PDF rather than an empty message.
    assert logs[1].attachments == logs[0].attachments


@pytest.mark.django_db
def test_a_second_document_sends_fresh_rather_than_resending(
    system_profile: SmtpProfile,
    property_: Property,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    sync_templates()
    first = _make_document(property_=property_, person=customer, gbp=gbp, terms=terms)
    _fire(first)

    second = BookingDocument.objects.create(booking=first.booking, kind="contract")
    second.file.save(f"{first.booking.reference}-contract-{second.pk}.pdf", ContentFile(PDF_BYTES))
    _fire(second)

    logs = EmailLog.objects.filter(template_key="booking.contract")
    assert logs.count() == 2
    second_log = logs.get(correlation__document_id=second.pk)
    assert "resent_from" not in second_log.correlation
    assert second_log.attachments[0]["storage_key"] == second.file.name


@pytest.mark.django_db
def test_resend_after_the_guest_email_is_corrected_goes_to_the_new_address(
    system_profile: SmtpProfile,
    property_: Property,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """`EmailService.resend` re-sends to the *original* row's recipients.

    A contract auto-sent to a mistyped address, then corrected by staff and
    resent, must not go to the old address again — and must certainly not
    stamp `sent_to_guest_at` as though the current guest received it.
    """
    sync_templates()
    document = _make_document(property_=property_, person=customer, gbp=gbp, terms=terms)
    _fire(document)

    customer.emails.update(email="ada.lovelace@example.com")
    _fire(document)

    logs = EmailLog.objects.filter(template_key="booking.contract").order_by("queued_at")
    assert [log.to for log in logs] == [["ada@example.com"], ["ada.lovelace@example.com"]]
    # A fresh send, not a resend: the correlation is the same but `to` differs,
    # which is already part of the idempotency key.
    assert "resent_from" not in logs[1].correlation
    assert logs[1].attachments == logs[0].attachments


@pytest.mark.django_db
def test_unreadable_attachment_is_skipped_not_raised(
    system_profile: SmtpProfile,
    property_: Property,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """The stored object is gone (an S3 lifecycle rule, a botched migration).

    Reading its size at send time hits storage, so this must degrade like any
    other infrastructure failure — the auto path wraps the receiver in a
    blanket `except` that would otherwise log `booking_document_failed`, which
    is a lie: the document generated and committed fine.
    """
    sync_templates()
    document = _make_document(property_=property_, person=customer, gbp=gbp, terms=terms)
    stored_key = document.file.name
    assert stored_key is not None
    storages["documents"].delete(stored_key)

    with structlog.testing.capture_logs() as logs:
        _fire(document)

    assert not EmailLog.objects.filter(template_key="booking.contract").exists()
    document.refresh_from_db()
    assert document.sent_to_guest_at is None
    assert any(
        entry["event"] == "comms.email_skipped" and entry.get("reason") == "attachment_unreadable"
        for entry in logs
    )


# ----------------------------------------------------------------------
# Skips — the stamp must never claim a delivery that didn't happen
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_guest_without_an_email_is_skipped_and_left_unstamped(
    system_profile: SmtpProfile,
    property_: Property,
    emailless_customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    sync_templates()
    document = _make_document(property_=property_, person=emailless_customer, gbp=gbp, terms=terms)

    with structlog.testing.capture_logs() as logs:
        _fire(document)

    assert not EmailLog.objects.filter(template_key="booking.contract").exists()
    document.refresh_from_db()
    assert document.sent_to_guest_at is None
    assert any(
        entry["event"] == "comms.email_skipped" and entry.get("reason") == "no_guest_email"
        for entry in logs
    )


@pytest.mark.django_db
def test_allowlist_blocked_send_leaves_the_row_unstamped(
    system_profile: SmtpProfile,
    property_: Property,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    sync_templates()
    document = _make_document(property_=property_, person=customer, gbp=gbp, terms=terms)

    with override_settings(EMAIL_RECIPIENT_ALLOWLIST=["@villacollective.com"]):
        _fire(document)

    log = EmailLog.objects.get(template_key="booking.contract")
    assert log.status == EmailLogStatus.BLOCKED
    document.refresh_from_db()
    assert document.sent_to_guest_at is None


@pytest.mark.django_db
def test_missing_template_is_logged_not_raised(
    system_profile: SmtpProfile,
    property_: Property,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """An unresolvable template degrades to a logged skip.

    Auto-generation fires this receiver from an `on_commit` callback, where a
    raised `EmailTemplateNotFound` would surface as an unhandled error on a
    request whose booking has already been confirmed.
    """
    EmailTemplate.objects.filter(key="booking.contract").update(is_active=False)
    document = _make_document(property_=property_, person=customer, gbp=gbp, terms=terms)

    with structlog.testing.capture_logs() as logs:
        _fire(document)

    assert not EmailLog.objects.filter(template_key="booking.contract").exists()
    document.refresh_from_db()
    assert document.sent_to_guest_at is None
    assert any(entry["event"] == "comms.email_skipped" for entry in logs)


@pytest.mark.django_db
def test_the_seed_migration_leaves_the_template_active(db: None) -> None:
    """`comms/0004` is what puts `booking.contract` in a deployed database.

    Without it the receiver's only symptom is a logged skip — a contract that
    silently never reaches the guest — so the migration is pinned here rather
    than only exercised through `sync_templates()` in the tests above.
    """
    assert EmailTemplate.objects.filter(key="booking.contract", is_active=True).exists()
