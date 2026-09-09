"""Generating and storing a booking's guest-facing documents (GAP-094).

`BookingDocumentService.generate` is the one way a `BookingDocument` row comes
into existence — staff `:generate`, and the auto-generation that rides
confirmation both land here, so a document always has a file behind it.

`auto_generate_contract` is the confirmation path's entry point. It is a plain
function, not a `@shared_task`: there is no Celery worker in any deployed
environment (staging runs `CELERY_TASK_ALWAYS_EAGER`, production has no worker
service), so a real task would queue to nothing. It is scheduled via
`transaction.on_commit` from the `booking_transitioned` receiver and **never
raises** — a PDF that won't render must not roll back a confirmed booking.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from core.exceptions import BookingDocumentNotAvailable, BookingDocumentSent
from core.logging.operations import log_operation
from reservations.enums import BookingDocumentKind
from reservations.models.booking_document import BookingDocument
from reservations.services.booking_contract_render import (
    render_contract_pdf,
    render_document_html,
)

if TYPE_CHECKING:
    from accounts.models import User
    from reservations.models.booking import Booking

logger = structlog.get_logger(__name__)


class BookingDocumentService:
    """Create `BookingDocument` rows with their rendered file attached."""

    @staticmethod
    def generate(
        booking: Booking,
        *,
        kind: str = BookingDocumentKind.CONTRACT.value,
        actor: User | None = None,
    ) -> BookingDocument:
        """Render `kind` for `booking` and store it as a new document row.

        Raises `UnsupportedDocumentKind` (400) for a kind the render seam
        doesn't know, and `BookingDocumentNotAvailable` (409) for a booking
        that has never been confirmed. Never overwrites an existing document:
        each call is a new row, so what a guest was sent stays retrievable.
        """
        if not booking.has_been_confirmed():
            raise BookingDocumentNotAvailable(
                f"A {kind} cannot be generated for a booking that has never been "
                f"confirmed (status {booking.status!r})."
            )
        # Renders (and validates the kind) before the row exists, so a bad
        # kind or a broken toolchain leaves nothing half-created behind.
        html = render_document_html(booking, kind)
        pdf = render_contract_pdf(booking, html=html)

        # The row is inserted to claim a pk, then updated with the file — one
        # transaction, so a fileless `BookingDocument` is never visible to a
        # concurrent reader.
        with transaction.atomic():
            document = BookingDocument.objects.create(
                booking=booking,
                kind=kind,
                generated_by=actor,
                created_by=actor,
            )
            # `pk`, not a per-booking count: two concurrent generates would
            # mint the same count and collide on the storage key.
            document.file.save(
                f"{booking.reference}-{kind}-{document.pk}.pdf",
                ContentFile(pdf),
                save=True,
            )
        logger.info(
            "reservations.booking_document_generated",
            booking_id=booking.pk,
            document_id=document.pk,
            kind=kind,
            size_bytes=len(pdf),
        )
        return document

    @staticmethod
    def delete(document: BookingDocument, *, actor: User | None = None) -> None:
        """Hard-delete an *unsent* document.

        Raises `BookingDocumentSent` (409) once `sent_to_guest_at` is set:
        `EmailLog.attachments` references the blob by storage key and a
        resend re-reads it, so a sent document is a record, not a draft.

        The guard runs on a row re-read under `select_for_update`, not on
        the instance the view loaded: a `:send` racing this call stamps the
        row between load and delete, and the whole point of the 409 is to
        keep exactly that row. A row already gone by then is a no-op — the
        other DELETE won and wrote the audit tombstone.

        `document.delete()` does the rest through signals: `core.audit.track`
        writes the `__deleted__` tombstone from `post_delete`, and
        `reservations.signals` releases the blob `on_commit` (a storage fault
        there is logged as `reservations.booking_document_blob_orphaned`,
        never raised). Nothing else points at `BookingDocument`.
        """
        with transaction.atomic():
            locked = BookingDocument.objects.select_for_update().filter(pk=document.pk).first()
            if locked is None:
                return
            if locked.sent_to_guest_at is not None:
                raise BookingDocumentSent(
                    "This document has been sent to the guest and cannot be deleted."
                )
            storage_key = locked.file.name or ""
            locked.delete()
        logger.info(
            "reservations.booking_document_deleted",
            booking_id=document.booking_id,
            document_id=document.pk,
            storage_key=storage_key,
            actor_id=getattr(actor, "pk", None),
        )


def auto_generate_contract(booking_pk: int) -> None:
    """Generate + request delivery of the contract for a just-confirmed booking.

    Swallows every failure: this runs from an `on_commit` callback after the
    booking transition has already committed, so raising would only surface as
    an unhandled error in the request (or, worse, break the response of a
    conversion that genuinely succeeded). A failure is logged as
    `reservations.booking_document_failed` and staff can generate the document
    by hand from the Documents tab.
    """
    if not settings.BOOKING_CONTRACT_AUTO_GENERATE:
        return

    from reservations.models.booking import Booking
    from reservations.signals import booking_document_send_requested

    try:
        with log_operation(
            "booking.contract_auto_generate", logger=logger, booking_id=booking_pk
        ) as ctx:
            booking = Booking.objects.select_related(
                "property__region__country", "terms_version", "person", "currency"
            ).get(pk=booking_pk)
            document = BookingDocumentService.generate(
                booking, kind=BookingDocumentKind.CONTRACT.value
            )
            ctx["document_id"] = document.pk
            # Deliberately OUTSIDE `generate`'s transaction. Storage is not
            # transactional, so a comms receiver that raises synchronously
            # would otherwise roll the row back and strand the PDF — guest PII
            # in a bucket with nothing pointing at it — while the log claimed
            # the render had failed. The document is committed first; a
            # delivery problem is then just a delivery problem.
            booking_document_send_requested.send(
                sender=BookingDocument, document=document, actor=None
            )
    except Exception:
        logger.exception("reservations.booking_document_failed", booking_id=booking_pk)
