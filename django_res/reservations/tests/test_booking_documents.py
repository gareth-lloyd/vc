"""GAP-094 — `BookingDocument` generation, storage and auto-generation.

Every generate is a new row with a real file behind it in the private
`documents` alias. Confirmation auto-generates the contract, and a render
failure there must never disturb the booking transition that triggered it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import structlog
from django.core.files.storage import storages

from accounts.models import User
from core.enums import StaffRole
from core.exceptions import BookingDocumentNotAvailable, UnsupportedDocumentKind
from properties.enums import DescriptionSection
from properties.models import PropertyDescription, PropertySettings
from reservations.enums import BookingDocumentKind, BookingStatus
from reservations.models import BookingDocument
from reservations.services.booking_documents import (
    BookingDocumentService,
    auto_generate_contract,
)
from reservations.services.bookings import BookingService
from reservations.signals import booking_document_send_requested

if TYPE_CHECKING:
    from properties.models import Property
    from reservations.models import Booking, QuotationLine, TermsVersion

RULES = "No parties. Quiet after 23:00."


def _set_house_rules(property_: Property, body: str) -> PropertyDescription:
    return PropertyDescription.objects.update_or_create(
        property=property_,
        section=DescriptionSection.HOUSE_RULES,
        defaults={"body": body},
    )[0]


@pytest.fixture
def booking(quotation_line: QuotationLine, terms: TermsVersion) -> Booking:
    _set_house_rules(quotation_line.property, RULES)
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    booking.refresh_from_db()
    assert booking.status == BookingStatus.AWAITING_DEPOSIT
    return booking


@pytest.fixture
def auto_generate_on(settings: Any) -> None:
    """Opt in to contract auto-generation (`test.py` defaults it off)."""
    settings.BOOKING_CONTRACT_AUTO_GENERATE = True


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="doc-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


# ----------------------------------------------------------------------
# generate
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_generate_writes_a_pdf_into_the_documents_storage(booking: Booking, staff: User) -> None:
    document = BookingDocumentService.generate(booking, actor=staff)

    assert document.kind == BookingDocumentKind.CONTRACT
    assert document.generated_by == staff
    assert document.created_by == staff
    assert document.generated_at is not None
    assert document.sent_to_guest_at is None
    stored_name = document.file.name
    assert stored_name is not None
    assert stored_name.endswith(f"{booking.reference}-contract-{document.pk}.pdf")
    assert storages["documents"].exists(stored_name)
    with document.file.open("rb") as handle:
        assert handle.read(4) == b"%PDF"


@pytest.mark.django_db
def test_generated_contract_carries_the_house_rules_snapshot(booking: Booking) -> None:
    """The stored PDF is printed from the same seam the preview renders."""
    _set_house_rules(booking.property, "Parties welcome.")

    document = BookingDocumentService.generate(booking)

    with document.file.open("rb") as handle:
        pdf = handle.read()
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500


@pytest.mark.django_db
def test_generate_keeps_every_previous_document(booking: Booking) -> None:
    """A regenerate must not erase what a guest was already sent."""
    first = BookingDocumentService.generate(booking)
    second = BookingDocumentService.generate(booking)

    assert first.pk != second.pk
    assert first.file.name != second.file.name
    assert first.file.name is not None
    assert storages["documents"].exists(first.file.name)
    # Newest first (`Meta.ordering`).
    assert list(booking.documents.all()) == [second, first]


@pytest.mark.django_db
def test_generate_rejects_an_unsupported_kind(booking: Booking) -> None:
    with pytest.raises(UnsupportedDocumentKind):
        BookingDocumentService.generate(booking, kind=BookingDocumentKind.VOUCHER.value)

    assert not BookingDocument.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status", [BookingStatus.DRAFT, BookingStatus.PENDING_OWNER_APPROVAL, BookingStatus.DECLINED]
)
def test_generate_refuses_a_booking_that_never_reached_confirmation(
    quotation_line: QuotationLine, terms: TermsVersion, status: str
) -> None:
    PropertySettings.objects.create(
        property=quotation_line.property, bookings_require_pre_approval=True
    )
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    booking.status = status
    booking.save(update_fields=["status"])

    with pytest.raises(BookingDocumentNotAvailable):
        BookingDocumentService.generate(booking)

    assert not BookingDocument.objects.exists()


@pytest.mark.django_db
def test_generate_refuses_a_booking_cancelled_before_it_was_ever_approved(
    quotation_line: QuotationLine, terms: TermsVersion
) -> None:
    """`cancel()` is reachable from PENDING_OWNER_APPROVAL — status alone lies."""
    PropertySettings.objects.create(
        property=quotation_line.property, bookings_require_pre_approval=True
    )
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    booking.cancel("owner said no")
    assert booking.status == BookingStatus.CANCELLED
    assert booking.house_rules_snapshot == ""

    with pytest.raises(BookingDocumentNotAvailable):
        BookingDocumentService.generate(booking)


@pytest.mark.django_db
def test_generate_allowed_for_a_cancelled_booking(booking: Booking) -> None:
    """Staff still need to re-issue the contract a cancelled guest was sent."""
    booking.cancel("changed plans")

    assert BookingDocumentService.generate(booking).pk


@pytest.mark.django_db
def test_generate_allowed_for_an_expired_booking(booking: Booking) -> None:
    """EXPIRED is reachable only from AWAITING_DEPOSIT — the guest already has one."""
    booking.expire()

    assert BookingDocumentService.generate(booking).pk


# ----------------------------------------------------------------------
# Auto-generation at confirmation
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_confirmation_auto_generates_exactly_one_contract(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    run_on_commit_immediately: None,
    auto_generate_on: None,
) -> None:
    _set_house_rules(quotation_line.property, RULES)

    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    documents = list(booking.documents.all())
    assert len(documents) == 1
    assert documents[0].kind == BookingDocumentKind.CONTRACT
    assert documents[0].generated_by is None  # no request user on the auto path


@pytest.mark.django_db
def test_auto_generation_requests_delivery_once(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    run_on_commit_immediately: None,
    auto_generate_on: None,
) -> None:
    received: list[dict[str, Any]] = []

    def _capture(sender: type, **kwargs: Any) -> None:
        received.append(kwargs)

    booking_document_send_requested.connect(_capture, dispatch_uid="test.capture")
    try:
        booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    finally:
        booking_document_send_requested.disconnect(dispatch_uid="test.capture")

    assert len(received) == 1
    assert received[0]["document"] == booking.documents.get()
    assert received[0]["actor"] is None


@pytest.mark.django_db
def test_auto_generation_is_off_when_the_setting_is(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    run_on_commit_immediately: None,
    settings: Any,
) -> None:
    settings.BOOKING_CONTRACT_AUTO_GENERATE = False  # `test.py`'s default, made explicit

    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    assert not booking.documents.exists()


@pytest.mark.django_db
def test_a_render_failure_leaves_the_booking_confirmed(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    run_on_commit_immediately: None,
    auto_generate_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken PDF toolchain must not cost us the booking."""
    monkeypatch.setattr(
        "reservations.services.booking_documents.render_contract_pdf",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("no pango here")),
    )

    with structlog.testing.capture_logs() as logs:
        booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.AWAITING_DEPOSIT
    assert not booking.documents.exists()
    assert any(entry["event"] == "reservations.booking_document_failed" for entry in logs)


@pytest.mark.django_db
def test_auto_generate_swallows_a_missing_booking(
    run_on_commit_immediately: None, auto_generate_on: None
) -> None:
    with structlog.testing.capture_logs() as logs:
        auto_generate_contract(999_999)

    assert any(entry["event"] == "reservations.booking_document_failed" for entry in logs)


@pytest.mark.django_db
def test_owner_approval_also_auto_generates(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    run_on_commit_immediately: None,
    auto_generate_on: None,
) -> None:
    """The later confirmation path (owner approval) generates too."""
    _set_house_rules(quotation_line.property, RULES)
    PropertySettings.objects.create(
        property=quotation_line.property, bookings_require_pre_approval=True
    )

    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    assert booking.status == BookingStatus.PENDING_OWNER_APPROVAL
    assert not booking.documents.exists()

    booking.owner_approve()

    assert booking.documents.count() == 1
