"""GAP-094 — the staff Documents API (`/bookings/{id}/documents…`).

Four verbs over one nested collection: list, generate, download, send. The
things worth pinning are not the happy paths but the edges the storage layer
introduces — a document row whose bytes have vanished from the bucket must be
a 409 an operator can act on, not a 500 — and the IDOR scope: every document
is reachable *only* through the URL of the booking that owns it.

Reads are open to any staff role; generate and send are writes
(`IsReservationsWriter`). `is_archived` is deliberately not filtered here: an
archived booking's issued documents are historical records staff must still be
able to fetch.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import TYPE_CHECKING, Any, cast

import pytest
import structlog
from botocore.exceptions import ClientError
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db.models import QuerySet
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from core.models import AuditLog
from properties.enums import DescriptionSection
from properties.models import PropertyDescription, PropertySettings
from reservations.enums import BookingDocumentKind, BookingStatus
from reservations.factories import make_occupying_booking
from reservations.models import Booking, BookingDocument
from reservations.services.bookings import BookingService

if TYPE_CHECKING:
    from accounts.models import Person
    from comms.models import SmtpProfile
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import QuotationLine, TermsVersion

PDF_BYTES = b"%PDF-1.7\nstored contract\n"
RULES = "No parties. Quiet after 23:00."


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="doc-api-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="doc-api-viewer@example.com",
        password="x",
        role=StaffRole.VIEWER,
    )


@pytest.fixture
def booking(quotation_line: QuotationLine, terms: TermsVersion) -> Booking:
    """A confirmed (AWAITING_DEPOSIT) booking with house rules to render."""
    PropertyDescription.objects.update_or_create(
        property=quotation_line.property,
        section=DescriptionSection.HOUSE_RULES,
        defaults={"body": RULES},
    )
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    booking.refresh_from_db()
    assert booking.status == BookingStatus.AWAITING_DEPOSIT
    return booking


@pytest.fixture
def other_booking(
    property_: Property, customer: Person, gbp: Currency, terms: TermsVersion
) -> Booking:
    return make_occupying_booking(
        property=property_,
        person=customer,
        currency=gbp,
        terms=terms,
        date_from=date(2027, 6, 10),
        date_to=date(2027, 6, 17),
    )


def _make_document(
    booking: Booking,
    *,
    kind: str = BookingDocumentKind.CONTRACT.value,
    content: bytes = PDF_BYTES,
) -> BookingDocument:
    """A stored document without paying for a WeasyPrint render.

    The generate *endpoint* exercises the real render seam once; every other
    test here is about routing, scoping and storage, so it buys its bytes
    cheaply.
    """
    document = BookingDocument.objects.create(booking=booking, kind=kind)
    document.file.save(
        f"{booking.reference}-{kind}-{document.pk}.pdf", ContentFile(content), save=True
    )
    return document


def _documents_url(booking: Booking) -> str:
    return f"/api/v1/bookings/{booking.pk}/documents"


def _access_denied(*_args: object, **_kwargs: object) -> None:
    """What S3 raises for a *missing* key when `ListBucket` is not granted.

    The documents bucket is hardened that way, so this — not a 404 — is the
    shape production sees when an object has been deleted out from under a row.
    """
    raise ClientError({"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}, "HeadObject")


def _body(response: object) -> bytes:
    """A `FileResponse` streams; the test client's stubs don't say so."""
    streaming = cast(StreamingHttpResponse, response)
    return b"".join(cast(Iterator[bytes], streaming.streaming_content))


# ----------------------------------------------------------------------
# List / detail
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_list_returns_the_bookings_documents_newest_first(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    first = _make_document(booking)
    second = _make_document(booking)

    api_client.force_login(staff)
    resp = api_client.get(_documents_url(booking))

    assert resp.status_code == 200, resp.data
    assert resp.data["count"] == 2
    # A regenerate does not replace what the guest was already sent; the newest
    # leads because that is the one staff are about to act on.
    assert [row["id"] for row in resp.data["results"]] == [second.pk, first.pk]


@pytest.mark.django_db
def test_list_is_scoped_to_the_booking(
    api_client: APIClient, staff: User, booking: Booking, other_booking: Booking
) -> None:
    mine = _make_document(booking)
    _make_document(other_booking)

    api_client.force_login(staff)
    resp = api_client.get(_documents_url(booking))

    assert resp.status_code == 200, resp.data
    assert [row["id"] for row in resp.data["results"]] == [mine.pk]


@pytest.mark.django_db
def test_detail_returns_the_documents_metadata(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    document = _make_document(booking)
    document.generated_by = staff
    document.save(update_fields=["generated_by"])

    api_client.force_login(staff)
    resp = api_client.get(f"{_documents_url(booking)}/{document.pk}")

    assert resp.status_code == 200, resp.data
    assert resp.data["id"] == document.pk
    assert resp.data["kind"] == BookingDocumentKind.CONTRACT.value
    assert resp.data["filename"] == f"{booking.reference}-contract-{document.pk}.pdf"
    assert resp.data["size"] == len(PDF_BYTES)
    assert resp.data["generated_at"] is not None
    assert resp.data["generated_by"] == {"id": staff.pk, "name": staff.email}
    assert resp.data["sent_to_guest_at"] is None


@pytest.mark.django_db
def test_a_document_is_404_under_another_bookings_url(
    api_client: APIClient, staff: User, booking: Booking, other_booking: Booking
) -> None:
    """The IDOR guard: the pk alone is not a capability."""
    document = _make_document(other_booking)

    api_client.force_login(staff)
    for path in (
        f"{_documents_url(booking)}/{document.pk}",
        f"{_documents_url(booking)}/{document.pk}:download",
    ):
        assert api_client.get(path).status_code == 404, path
    assert api_client.post(f"{_documents_url(booking)}/{document.pk}:send").status_code == 404


@pytest.mark.django_db
def test_an_archived_bookings_documents_stay_readable(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """Archiving hides a booking from the working list, not its issued papers."""
    document = _make_document(booking)
    booking.is_archived = True
    booking.save(update_fields=["is_archived"])

    api_client.force_login(staff)
    assert api_client.get(_documents_url(booking)).data["count"] == 1
    assert api_client.get(f"{_documents_url(booking)}/{document.pk}").status_code == 200
    assert api_client.get(f"{_documents_url(booking)}/{document.pk}:download").status_code == 200


@pytest.mark.django_db
def test_a_vanished_file_does_not_break_the_list(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """`size` degrades to null instead of 500-ing the whole tab.

    The row is the only evidence the document ever existed, so it has to stay
    visible — that is what staff regenerate from.
    """
    document = _make_document(booking)
    stored_key = document.file.name
    assert stored_key is not None
    document.file.storage.delete(stored_key)

    api_client.force_login(staff)
    resp = api_client.get(_documents_url(booking))

    assert resp.status_code == 200, resp.data
    assert resp.data["results"][0]["id"] == document.pk
    assert resp.data["results"][0]["size"] is None
    assert resp.data["results"][0]["filename"].endswith(".pdf")


@pytest.mark.django_db
def test_a_storage_error_that_is_not_a_clean_404_still_does_not_break_the_list(
    api_client: APIClient, staff: User, booking: Booking, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guarantee above has to hold on S3, not just on the filesystem.

    django-storages translates only an HTTP 404 into `FileNotFoundError` and
    re-raises every other `ClientError`, and the hardened bucket policy answers
    a missing key with 403 — so catching `OSError` alone would 500 the entire
    Documents tab in the one environment that matters.
    """
    document = _make_document(booking)
    monkeypatch.setattr(type(document.file.storage), "size", _access_denied)

    api_client.force_login(staff)
    resp = api_client.get(_documents_url(booking))

    assert resp.status_code == 200, resp.data
    assert resp.data["results"][0]["id"] == document.pk
    assert resp.data["results"][0]["size"] is None


@pytest.mark.django_db
def test_listing_documents_for_an_unknown_booking_is_404(
    api_client: APIClient, staff: User
) -> None:
    """All the document routes agree about a bad booking id.

    An empty 200 renders the tab's "no documents yet — generate one" state on a
    mistyped or deleted id, and the Generate click that follows then 404s with
    nothing on screen to explain it.
    """
    api_client.force_login(staff)

    resp = api_client.get("/api/v1/bookings/9999999/documents")

    assert resp.status_code == 404


# ----------------------------------------------------------------------
# :generate
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_generate_renders_a_contract_and_returns_201(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    api_client.force_login(staff)
    resp = api_client.post(
        f"{_documents_url(booking)}:generate", {"kind": "contract"}, format="json"
    )

    assert resp.status_code == 201, resp.data
    document = BookingDocument.objects.get()
    assert resp.data["id"] == document.pk
    assert resp.data["generated_by"]["id"] == staff.pk
    assert document.generated_by == staff
    assert document.file.read().startswith(b"%PDF")


@pytest.mark.django_db
def test_generate_defaults_to_the_contract_kind(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    api_client.force_login(staff)
    resp = api_client.post(f"{_documents_url(booking)}:generate", {}, format="json")

    assert resp.status_code == 201, resp.data
    assert resp.data["kind"] == BookingDocumentKind.CONTRACT.value


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["voucher", "banana"])
def test_generate_with_an_unsupported_kind_is_400(
    api_client: APIClient, staff: User, booking: Booking, kind: str
) -> None:
    """A named-but-unbuilt kind and pure nonsense fail the same way.

    `kind` is a plain `CharField`, not a `ChoiceField`: the render seam owns
    the list of kinds that actually exist, so the enum can name `voucher`
    without the API claiming it can produce one.
    """
    api_client.force_login(staff)
    resp = api_client.post(f"{_documents_url(booking)}:generate", {"kind": kind}, format="json")

    assert resp.status_code == 400, resp.data
    assert resp.data["code"] == "unsupported_kind"
    assert not BookingDocument.objects.exists()


@pytest.mark.django_db
def test_generate_for_a_booking_that_was_never_confirmed_is_409(
    api_client: APIClient, staff: User, quotation_line: QuotationLine, terms: TermsVersion
) -> None:
    PropertySettings.objects.create(
        property=quotation_line.property, bookings_require_pre_approval=True
    )
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    assert booking.status == BookingStatus.PENDING_OWNER_APPROVAL

    api_client.force_login(staff)
    resp = api_client.post(f"{_documents_url(booking)}:generate", {}, format="json")

    assert resp.status_code == 409, resp.data
    assert resp.data["code"] == "document_not_available"
    assert not BookingDocument.objects.exists()


@pytest.mark.django_db
def test_generate_against_an_unknown_booking_is_404(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)
    assert (
        api_client.post("/api/v1/bookings/999999/documents:generate", {}, format="json").status_code
        == 404
    )


# ----------------------------------------------------------------------
# :download
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_download_streams_the_stored_pdf_as_an_attachment(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    document = _make_document(booking)

    api_client.force_login(staff)
    resp = api_client.get(f"{_documents_url(booking)}/{document.pk}:download")

    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    filename = f"{booking.reference}-contract-{document.pk}.pdf"
    # `attachment`, not `inline`: the bytes carry guest PII and must never be
    # rendered by a browser at a URL someone could paste into a chat.
    assert resp["Content-Disposition"] == f'attachment; filename="{filename}"'
    assert _body(resp) == PDF_BYTES


@pytest.mark.django_db
def test_download_of_a_document_whose_bytes_have_vanished_is_409(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """A file deleted out from under the row is an operator problem, not a 500.

    `409 document_file_missing` tells the Documents tab to offer "regenerate";
    a 404 would be indistinguishable from "no such document".
    """
    document = _make_document(booking)
    stored_key = document.file.name
    assert stored_key is not None
    document.file.storage.delete(stored_key)

    api_client.force_login(staff)
    resp = api_client.get(f"{_documents_url(booking)}/{document.pk}:download")

    assert resp.status_code == 409, resp.data
    assert resp.data["code"] == "document_file_missing"


# ----------------------------------------------------------------------
# :send
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_send_emails_the_document_and_stamps_it(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    system_profile: SmtpProfile,
    run_on_commit_immediately: None,
) -> None:
    from comms.models import EmailLog

    document = _make_document(booking)

    api_client.force_login(staff)
    resp = api_client.post(f"{_documents_url(booking)}/{document.pk}:send")

    assert resp.status_code == 200, resp.data
    assert resp.data["sent_to_guest_at"] is not None
    document.refresh_from_db()
    assert document.sent_to_guest_at is not None
    log = EmailLog.objects.get(template_key="booking.contract")
    assert log.correlation == {"booking_id": booking.pk, "document_id": document.pk}
    assert log.attachments[0]["storage"] == "documents"


@pytest.mark.django_db
def test_a_second_send_mints_a_second_email(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    system_profile: SmtpProfile,
    run_on_commit_immediately: None,
) -> None:
    """Staff pressing "send" twice must actually send twice (resend path)."""
    from comms.models import EmailLog

    document = _make_document(booking)
    api_client.force_login(staff)
    url = f"{_documents_url(booking)}/{document.pk}:send"

    assert api_client.post(url).status_code == 200
    assert api_client.post(url).status_code == 200

    assert EmailLog.objects.filter(template_key="booking.contract").count() == 2


@pytest.mark.django_db
def test_send_to_a_guest_with_no_email_is_409(
    api_client: APIClient, staff: User, booking: Booking, system_profile: SmtpProfile
) -> None:
    """Refused up front rather than 200-with-a-null-stamp.

    The comms receiver degrades a missing address to a logged skip — right for
    the automatic path, wrong for a staff member who just clicked "send" and
    needs to be told why nothing happened.
    """
    booking.person.emails.all().delete()

    api_client.force_login(staff)
    document = _make_document(booking)
    resp = api_client.post(f"{_documents_url(booking)}/{document.pk}:send")

    assert resp.status_code == 409, resp.data
    assert resp.data["code"] == "no_recipient"
    document.refresh_from_db()
    assert document.sent_to_guest_at is None


@pytest.mark.django_db
def test_send_of_a_document_whose_bytes_have_vanished_is_409(
    api_client: APIClient, staff: User, booking: Booking, system_profile: SmtpProfile
) -> None:
    from comms.models import EmailLog

    document = _make_document(booking)
    stored_key = document.file.name
    assert stored_key is not None
    document.file.storage.delete(stored_key)

    api_client.force_login(staff)
    resp = api_client.post(f"{_documents_url(booking)}/{document.pk}:send")

    assert resp.status_code == 409, resp.data
    assert resp.data["code"] == "document_file_missing"
    assert not EmailLog.objects.filter(template_key="booking.contract").exists()


@pytest.mark.django_db
def test_send_reports_an_unreadable_stored_file_as_missing(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    system_profile: SmtpProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`S3Storage.exists` returns False only on a 404 and re-raises otherwise.

    Without this the 409 the test above pins is a 500 under the bucket policy
    production runs, for exactly the case an operator can fix.
    """
    document = _make_document(booking)
    monkeypatch.setattr(type(document.file.storage), "exists", _access_denied)

    api_client.force_login(staff)
    resp = api_client.post(f"{_documents_url(booking)}/{document.pk}:send")

    assert resp.status_code == 409, resp.data
    assert resp.data["code"] == "document_file_missing"


@pytest.mark.django_db
def test_a_send_that_never_reaches_the_mail_pipeline_is_409(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    system_profile: SmtpProfile,
    run_on_commit_immediately: None,
    settings: Any,
) -> None:
    """No silent 200 for the failures the endpoint cannot pre-check.

    The recipient allowlist is one of several ways the receiver correctly
    declines to deliver — an unseeded or deactivated template, no SMTP profile
    and a render error are the others, and every one of them leaves
    `sent_to_guest_at` untouched. Staff who just clicked Send have to be told,
    or the tab renders success and they click forever.
    """
    settings.EMAIL_RECIPIENT_ALLOWLIST = ["ops@villacollective.test"]
    document = _make_document(booking)

    api_client.force_login(staff)
    resp = api_client.post(f"{_documents_url(booking)}/{document.pk}:send")

    assert resp.status_code == 409, resp.data
    assert resp.data["code"] == "document_send_failed"
    document.refresh_from_db()
    assert document.sent_to_guest_at is None


@pytest.mark.django_db
def test_a_failed_resend_does_not_report_the_earlier_send(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    system_profile: SmtpProfile,
    run_on_commit_immediately: None,
    settings: Any,
) -> None:
    """A failure does not *clear* the stamp, so "is it null" is the wrong test.

    A resend that never reaches the pipeline leaves the first send's timestamp
    on the row; only comparing against the value captured before the signal
    makes the second call a 409 rather than a 200 quoting a delivery that
    happened days ago.
    """
    document = _make_document(booking)
    api_client.force_login(staff)
    url = f"{_documents_url(booking)}/{document.pk}:send"
    assert api_client.post(url).status_code == 200
    document.refresh_from_db()
    first_stamp = document.sent_to_guest_at
    assert first_stamp is not None

    settings.EMAIL_RECIPIENT_ALLOWLIST = ["ops@villacollective.test"]
    resp = api_client.post(url)

    assert resp.status_code == 409, resp.data
    assert resp.data["code"] == "document_send_failed"
    document.refresh_from_db()
    assert document.sent_to_guest_at == first_stamp


# ----------------------------------------------------------------------
# Permissions
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_viewer_can_read_and_download_but_not_generate_or_send(
    api_client: APIClient, viewer: User, booking: Booking
) -> None:
    document = _make_document(booking)
    api_client.force_login(viewer)

    assert api_client.get(_documents_url(booking)).status_code == 200
    assert api_client.get(f"{_documents_url(booking)}/{document.pk}").status_code == 200
    assert api_client.get(f"{_documents_url(booking)}/{document.pk}:download").status_code == 200

    assert (
        api_client.post(f"{_documents_url(booking)}:generate", {}, format="json").status_code == 403
    )
    assert api_client.post(f"{_documents_url(booking)}/{document.pk}:send").status_code == 403
    assert BookingDocument.objects.count() == 1


@pytest.mark.django_db
def test_anonymous_callers_are_refused(api_client: APIClient, booking: Booking) -> None:
    document = _make_document(booking)

    assert api_client.get(_documents_url(booking)).status_code == 403
    assert api_client.get(f"{_documents_url(booking)}/{document.pk}:download").status_code == 403


@pytest.mark.django_db
def test_a_non_staff_principal_is_refused(
    api_client: APIClient, booking: Booking, customer: Person
) -> None:
    """An owner-portal user carries `role=VIEWER` but is not staff (GAP-013)."""
    owner_user = User.objects.create_user(email="owner-doc@example.com", password="x")
    assert not owner_user.is_staff
    document = _make_document(booking)

    api_client.force_login(owner_user)
    assert api_client.get(_documents_url(booking)).status_code == 403
    assert api_client.get(f"{_documents_url(booking)}/{document.pk}:download").status_code == 403


@pytest.mark.django_db
def test_generate_is_recorded_against_the_acting_user(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """`generated_by` is the audit trail the serializer exposes to the tab."""
    api_client.force_login(staff)
    resp = cast(Any, api_client.post(f"{_documents_url(booking)}:generate", {}, format="json"))

    document = BookingDocument.objects.get(pk=resp.data["id"])
    assert document.generated_by == staff
    assert document.created_by == staff


# ----------------------------------------------------------------------
# DELETE — only an unsent document (GAP-094 retro)
# ----------------------------------------------------------------------
def _audit_rows_for(document_pk: int) -> QuerySet[AuditLog]:
    ct = ContentType.objects.get_for_model(BookingDocument)
    return AuditLog.objects.filter(content_type=ct, object_id=str(document_pk))


@pytest.mark.django_db
def test_delete_removes_an_unsent_document_its_file_and_leaves_an_audit_trail(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    django_capture_on_commit_callbacks: Any,
) -> None:
    """The remedy for a double-submitted `:generate`: the duplicate is the
    unsent one. Row goes inside the transaction (the audit tombstone comes
    from `track`), the blob goes after commit."""
    document = _make_document(booking)
    stored_key = document.file.name
    assert stored_key
    storage = document.file.storage
    assert storage.exists(stored_key)
    api_client.force_login(staff)

    with django_capture_on_commit_callbacks(execute=True):
        resp = api_client.delete(f"{_documents_url(booking)}/{document.pk}")

    assert resp.status_code == 204, resp.data
    assert not BookingDocument.objects.filter(pk=document.pk).exists()
    assert _audit_rows_for(document.pk).latest("created_at").field_diffs["__deleted__"] is True
    assert not storage.exists(stored_key)


@pytest.mark.django_db
def test_delete_still_succeeds_when_the_blob_cannot_be_removed(
    api_client: APIClient,
    staff: User,
    booking: Booking,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: Any,
) -> None:
    """An orphaned blob beats a dangling row: the row is gone by the time the
    storage call runs, so a storage fault is logged, not raised."""
    document = _make_document(booking)
    stored_key = document.file.name
    storage = document.file.storage

    def _refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError("storage refused the delete")

    monkeypatch.setattr(type(storage), "delete", _refuse)
    api_client.force_login(staff)

    with structlog.testing.capture_logs() as logs, django_capture_on_commit_callbacks(execute=True):
        resp = api_client.delete(f"{_documents_url(booking)}/{document.pk}")

    assert resp.status_code == 204
    assert not BookingDocument.objects.filter(pk=document.pk).exists()
    orphaned = [
        entry for entry in logs if entry["event"] == "reservations.booking_document_blob_orphaned"
    ]
    assert orphaned and orphaned[0]["storage_key"] == stored_key


@pytest.mark.django_db
def test_delete_of_a_sent_document_is_409_and_removes_nothing(
    api_client: APIClient, staff: User, booking: Booking
) -> None:
    """The EmailLog that sent it references the blob by storage key and a
    resend re-reads it, so a sent document is a historical record."""
    document = _make_document(booking)
    document.sent_to_guest_at = timezone.now()
    document.save(update_fields=["sent_to_guest_at"])
    stored_key = document.file.name
    assert stored_key
    api_client.force_login(staff)

    resp = api_client.delete(f"{_documents_url(booking)}/{document.pk}")

    assert resp.status_code == 409, resp.data
    assert resp.data["code"] == "document_sent"
    assert resp.data["detail"] == "This document has been sent to the guest and cannot be deleted."
    assert BookingDocument.objects.filter(pk=document.pk).exists()
    assert document.file.storage.exists(stored_key)
    assert not _audit_rows_for(document.pk).filter(field_diffs__has_key="__deleted__").exists()


@pytest.mark.django_db
def test_delete_guard_reads_the_row_under_lock_not_the_loaded_instance(
    api_client: APIClient, staff: User, booking: Booking, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `:send` racing the DELETE stamps the row after the view loaded it.
    The guard must see the stamp — the 409 exists to keep exactly that row."""
    from reservations.services import booking_documents as svc

    document = _make_document(booking)
    real_delete = svc.BookingDocumentService.delete

    def _stamp_then_delete(doc: BookingDocument, **kwargs: Any) -> None:
        # The race, made deterministic: the send lands between the view's
        # load and the service's locked re-read.
        BookingDocument.objects.filter(pk=doc.pk).update(sent_to_guest_at=timezone.now())
        real_delete(doc, **kwargs)

    monkeypatch.setattr(svc.BookingDocumentService, "delete", staticmethod(_stamp_then_delete))
    api_client.force_login(staff)

    resp = api_client.delete(f"{_documents_url(booking)}/{document.pk}")

    assert resp.status_code == 409, resp.data
    assert BookingDocument.objects.filter(pk=document.pk).exists()


@pytest.mark.django_db
def test_delete_is_404_under_another_bookings_url(
    api_client: APIClient, staff: User, booking: Booking, other_booking: Booking
) -> None:
    document = _make_document(booking)
    api_client.force_login(staff)

    resp = api_client.delete(f"{_documents_url(other_booking)}/{document.pk}")

    assert resp.status_code == 404
    assert BookingDocument.objects.filter(pk=document.pk).exists()


@pytest.mark.django_db
def test_delete_is_refused_for_viewers_and_anonymous_callers(
    api_client: APIClient, viewer: User, booking: Booking
) -> None:
    document = _make_document(booking)
    url = f"{_documents_url(booking)}/{document.pk}"

    assert api_client.delete(url).status_code == 403

    api_client.force_login(viewer)
    assert api_client.delete(url).status_code == 403
    assert BookingDocument.objects.filter(pk=document.pk).exists()
