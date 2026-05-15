"""HoldService — Python-level lifecycle for `BookingHold` rows.

The DB-level `EXCLUDE` constraint is Postgres-only. On SQLite (used by
the test suite) we fall back to a Python overlap check before insert.

All mutations run inside `transaction.atomic` so the place/release
operations remain consistent even if a later step in the calling service
fails.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from core.exceptions import HoldUnavailable
from reservations.enums import BookingHoldReason
from reservations.models.booking import BookingHold

if TYPE_CHECKING:
    from datetime import date as date_type


class HoldService:
    """Place / release / expire `BookingHold` rows."""

    @classmethod
    def _has_overlapping_live_hold(
        cls,
        *,
        property: Any,
        date_from: date_type,
        date_to: date_type,
        exclude_hold_ids: list[int] | None = None,
    ) -> bool:
        """Check Python-side whether any live hold overlaps the requested range."""
        return BookingHold.live_overlapping(
            property=property,
            date_from=date_from,
            date_to=date_to,
            exclude_ids=exclude_hold_ids,
        ).exists()

    @classmethod
    @transaction.atomic
    def place(
        cls,
        *,
        property: Any,
        date_from: date_type,
        date_to: date_type,
        expires_at: datetime,
        reason: str = BookingHoldReason.MANUAL.value,
        quotation: Any = None,
        booking: Any = None,
    ) -> BookingHold:
        """Place a live hold; raises `HoldUnavailable` if one already overlaps."""
        if cls._has_overlapping_live_hold(
            property=property,
            date_from=date_from,
            date_to=date_to,
        ):
            raise HoldUnavailable(
                f"An overlapping live hold already exists for property {property.pk} "
                f"on {date_from}..{date_to}"
            )
        return BookingHold.objects.create(
            property=property,
            quotation=quotation,
            booking=booking,
            date_from=date_from,
            date_to=date_to,
            expires_at=expires_at,
            reason=reason,
        )

    @classmethod
    @transaction.atomic
    def release(cls, hold: BookingHold) -> BookingHold:
        """Mark a single hold as released right now."""
        if hold.released_at is not None:
            return hold
        hold.released_at = timezone.now()
        hold.save(update_fields=["released_at", "updated_at"])
        return hold

    @classmethod
    @transaction.atomic
    def release_for_quotation(cls, quotation: Any) -> int:
        """Release every live hold tied to a given quotation. Returns count."""
        now = timezone.now()
        return BookingHold.objects.filter(
            quotation=quotation,
            released_at__isnull=True,
        ).update(released_at=now)

    @classmethod
    @transaction.atomic
    def release_for_booking(cls, booking: Any) -> int:
        """Release every live hold tied to a given booking. Returns count."""
        now = timezone.now()
        return BookingHold.objects.filter(
            booking=booking,
            released_at__isnull=True,
        ).update(released_at=now)

    @classmethod
    def expire_due(cls) -> list[int]:
        """Mark holds past their `expires_at` as released; return ids touched.

        The actual signal fan-out happens in `reservations.tasks.expire_holds`.
        This helper is the underlying DB operation.
        """
        now = timezone.now()
        due_ids = list(
            BookingHold.objects.filter(
                released_at__isnull=True,
                expires_at__lt=now,
            ).values_list("pk", flat=True)
        )
        if not due_ids:
            return []
        BookingHold.objects.filter(pk__in=due_ids).update(released_at=now)
        return due_ids
