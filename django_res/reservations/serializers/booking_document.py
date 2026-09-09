"""Booking document serializers (GAP-094)."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from rest_framework import serializers

from reservations.enums import BookingDocumentKind
from reservations.models import BookingDocument
from reservations.storage import DOCUMENT_READ_ERRORS


class BookingDocumentSerializer(serializers.ModelSerializer[BookingDocument]):
    """Metadata for one generated document — never its bytes.

    The file itself only ever leaves through `:download`, which streams it
    behind the staff permission; there is no URL field here because the
    `documents` storage alias has no public URL by design.
    """

    filename = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    generated_by = serializers.SerializerMethodField()

    class Meta:
        model = BookingDocument
        fields = [
            "id",
            "kind",
            "filename",
            "size",
            "generated_at",
            "generated_by",
            "sent_to_guest_at",
        ]
        read_only_fields = fields

    def get_filename(self, obj: BookingDocument) -> str:
        """The basename staff see, not the storage key (a dated prefix)."""
        return PurePosixPath(obj.file.name or "").name

    def get_size(self, obj: BookingDocument) -> int | None:
        """Byte count, or `None` when the stored object can't be reached.

        Read from storage rather than a column: a booking's document list is a
        handful of rows, so the round trips are bounded, and a derived value
        cannot drift from the file it describes. `None` (rather than an
        exception) matters — a document whose bytes have vanished must still
        appear in the list, so staff can see it exists and regenerate it. That
        is why the guard is `DOCUMENT_READ_ERRORS` and not just `OSError`: on
        S3 the ordinary vanished-object case is a `ClientError`, and letting it
        out of here would 500 the whole Documents tab over one bad row.
        """
        if not obj.file.name:
            return None
        try:
            return obj.file.size
        except DOCUMENT_READ_ERRORS:
            return None

    def get_generated_by(self, obj: BookingDocument) -> dict[str, Any] | None:
        user = obj.generated_by
        if user is None:
            # The auto-generation path runs from an `on_commit` callback with
            # no request user behind it — "the system issued this".
            return None
        return {"id": user.pk, "name": user.get_full_name().strip() or user.email}


class BookingDocumentGenerateSerializer(serializers.Serializer[BookingDocument]):
    """`POST …/documents:generate` body.

    `kind` is a plain `CharField`, deliberately not a `ChoiceField`:
    `BookingDocumentKind` names every document the spec plans, but only
    `contract` has a render behind it today. The render seam owns that
    distinction and answers with `unsupported_kind` (400), so the API never
    claims it can produce a voucher just because the enum spells one.
    """

    kind = serializers.CharField(
        required=False, default=BookingDocumentKind.CONTRACT.value, max_length=32
    )
