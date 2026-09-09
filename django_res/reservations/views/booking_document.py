"""Nested booking-document endpoints (`/bookings/{id}/documents…`, GAP-094).

Every view resolves its document through the booking in the URL, so a document
pk is not a capability on its own — a cross-booking id 404s rather than
handing over another guest's contract.

`is_archived` is deliberately *not* filtered (unlike `BookingViewSet`): an
archived booking's issued documents are historical records, and archiving is a
"stop showing me this in the working list" gesture, not a retraction of what a
guest was sent.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, cast

from django.db.models import QuerySet
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.permissions import IsReservationsWriter
from core.exceptions import (
    BookingDocumentFileMissing,
    DocumentSendFailed,
    NoDocumentRecipient,
)
from reservations.models import Booking, BookingDocument
from reservations.serializers.booking_document import (
    BookingDocumentGenerateSerializer,
    BookingDocumentSerializer,
)
from reservations.services.booking_documents import BookingDocumentService
from reservations.signals import booking_document_send_requested
from reservations.storage import DOCUMENT_READ_ERRORS

if TYPE_CHECKING:
    from accounts.models import User


def _scoped_documents(booking_pk: int) -> QuerySet[BookingDocument]:
    """This booking's documents, newest first (model `Meta.ordering`)."""
    return BookingDocument.objects.filter(booking_id=booking_pk).select_related("generated_by")


def _require_stored_file(document: BookingDocument) -> None:
    """Refuse up front when the row's bytes are not in the bucket.

    Checked before anything irreversible happens (an email on the wire): the
    comms receiver degrades an unreadable attachment to a logged skip, which
    would leave a staff member looking at a 200 and a null stamp.

    `exists()` is guarded because it does not fail closed: `S3Storage.exists`
    returns False only for a 404 and re-raises every other `ClientError` — and
    a missing key in the documents bucket answers 403, not 404. Unguarded, the
    409 this function exists to raise would be a 500 in production and nowhere
    else. See `DOCUMENT_READ_ERRORS`.
    """
    name = document.file.name
    if not name:
        raise BookingDocumentFileMissing(
            f"Document {document.pk} has no stored file; regenerate it before sending."
        )
    try:
        stored = document.file.storage.exists(name)
    except DOCUMENT_READ_ERRORS as exc:
        raise BookingDocumentFileMissing(
            f"Document {document.pk}'s stored file could not be read; regenerate it."
        ) from exc
    if not stored:
        raise BookingDocumentFileMissing(
            f"Document {document.pk} has no stored file; regenerate it before sending."
        )


def _require_recipient(booking: Booking) -> None:
    """Refuse a send to a booking whose guest has no email address.

    Reads `Person.primary_email()` — the same canonical resolver
    `comms.recipients.recipient_email` delegates to (and which fails closed for
    an anonymised Person). Called directly because `reservations` cannot import
    `comms`; `accounts` is a clean downward edge on the import spine.
    """
    person = booking.person
    if person is None or not person.primary_email():
        raise NoDocumentRecipient(
            f"Booking {booking.reference} has no guest email address to send to."
        )


class BookingDocumentListView(generics.ListAPIView):
    """`GET …/documents` — the booking's documents, newest first."""

    serializer_class = BookingDocumentSerializer
    permission_classes = [IsAuthenticated, IsReservationsWriter]

    def get_queryset(self) -> QuerySet[BookingDocument]:
        # 404 on an unknown booking so all five routes agree about a bad id.
        # An empty 200 renders the tab's "no documents yet — generate one"
        # state on a mistyped or deleted booking, and the Generate click that
        # follows then 404s with nothing on screen to explain it.
        get_object_or_404(Booking.objects.only("pk"), pk=self.kwargs["booking_pk"])
        return _scoped_documents(self.kwargs["booking_pk"])


class BookingDocumentDetailView(generics.RetrieveAPIView):
    """`GET …/documents/{id}` — one document's metadata."""

    serializer_class = BookingDocumentSerializer
    permission_classes = [IsAuthenticated, IsReservationsWriter]
    lookup_url_kwarg = "document_id"

    def get_queryset(self) -> QuerySet[BookingDocument]:
        return _scoped_documents(self.kwargs["booking_pk"])


class BookingDocumentGenerateView(APIView):
    """`POST …/documents:generate` — render and store a new document.

    Always a new row: a contract already emailed to a guest is the record of
    what they were sent, so a regenerate after a correction sits alongside it
    rather than overwriting it.
    """

    permission_classes = [IsAuthenticated, IsReservationsWriter]

    def post(self, request: Request, booking_pk: int, *args: Any, **kwargs: Any) -> Response:
        booking = get_object_or_404(
            Booking.objects.select_related(
                "property__region__country", "terms_version", "person", "currency"
            ),
            pk=booking_pk,
        )
        body = BookingDocumentGenerateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        document = BookingDocumentService.generate(
            # `IsAuthenticated` has already run — the actor is a real user.
            booking,
            kind=body.validated_data["kind"],
            actor=cast("User", request.user),
        )
        return Response(BookingDocumentSerializer(document).data, status=status.HTTP_201_CREATED)


class BookingDocumentDownloadView(APIView):
    """`GET …/documents/{id}:download` — stream the PDF to the operator.

    The bytes never get a URL of their own: the `documents` storage alias is
    private precisely because a contract carries guest PII, so the download
    goes through the staff permission on every request rather than handing out
    a link that outlives the session.
    """

    permission_classes = [IsAuthenticated, IsReservationsWriter]

    def get(
        self, request: Request, booking_pk: int, document_id: int, *args: Any, **kwargs: Any
    ) -> FileResponse:
        document = get_object_or_404(_scoped_documents(booking_pk), pk=document_id)
        try:
            handle = document.file.open("rb")
        except DOCUMENT_READ_ERRORS as exc:
            # `S3File.__init__` loads the object eagerly, so this fires on S3
            # rather than half-way through streaming a response whose status
            # line has already gone out. Same read rule as the list and the
            # send pre-check — see `DOCUMENT_READ_ERRORS` for why a non-404
            # `ClientError` is reported as a missing file and not a 500.
            raise BookingDocumentFileMissing(
                f"Document {document.pk} has no stored file; regenerate it."
            ) from exc
        return FileResponse(
            handle,
            content_type="application/pdf",
            as_attachment=True,
            filename=PurePosixPath(document.file.name or "").name,
        )


class BookingDocumentSendView(APIView):
    """`POST …/documents/{id}:send` — email an existing document to the guest.

    Emits `booking_document_send_requested`; the comms receiver owns the
    send-or-resend decision and stamps `sent_to_guest_at`. The two failures a
    staff member can actually fix — no guest address, no stored file — are
    refused here as 409s naming the cause, because the receiver's
    degrade-and-log behaviour (correct for the automatic path) would show up as
    a silent 200. The rest (an unseeded or deactivated template, no SMTP
    profile, a render error, an allowlist block) are indistinguishable from
    here without importing `comms`, so they are caught by their effect: the
    stamp is the receiver's one visible "the mail pipeline took it".
    """

    permission_classes = [IsAuthenticated, IsReservationsWriter]

    def post(
        self, request: Request, booking_pk: int, document_id: int, *args: Any, **kwargs: Any
    ) -> Response:
        document = get_object_or_404(
            _scoped_documents(booking_pk).select_related("booking__person"),
            pk=document_id,
        )
        _require_recipient(document.booking)
        _require_stored_file(document)
        # Captured, not compared against null: a failure never *clears* the
        # stamp, so a resend that died on the way to the pipeline would
        # otherwise answer 200 quoting the first send's timestamp — worse than
        # a null, because it reads as a fresh delivery.
        stamped_before = document.sent_to_guest_at
        booking_document_send_requested.send(
            sender=BookingDocument, document=document, actor=request.user
        )
        document.refresh_from_db()
        if document.sent_to_guest_at == stamped_before:
            raise DocumentSendFailed(
                f"Document {document.pk} could not be emailed; see the booking's "
                f"email log for the reason."
            )
        return Response(BookingDocumentSerializer(document).data)
