"""OwnerBlockService — lifecycle for owner availability-block requests.

A request reserves nothing while PENDING. Approval is where the real
(indefinite) `BookingHold` is placed, so the overlap check that matters runs at
*approve* time, not submit time: a booking could land in the requested range
between submission and review. `HoldService.place` only guards against
overlapping *holds* — no DB constraint spans the bookings↔holds tables — so the
service explicitly rejects when a live booking occupies the range too.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from core.exceptions import HoldUnavailable, InvalidTransition, OverlappingBooking
from reservations.enums import (
    BookingHoldReason,
    OwnerBlockKind,
    OwnerBlockStatus,
)
from reservations.models import Booking, BookingHold, OwnerBlock
from reservations.services.holds import HoldService

if TYPE_CHECKING:
    from accounts.models import User
    from properties.models import Property

_KIND_TO_HOLD_REASON = {
    OwnerBlockKind.MAINTENANCE.value: BookingHoldReason.MAINTENANCE.value,
}
_DEFAULT_HOLD_REASON = BookingHoldReason.OWNER_BLOCK.value


class OwnerBlockService:
    """Create / approve / decline / cancel owner block requests."""

    @staticmethod
    def _assert_range_free(
        *,
        property: Property,
        date_from: date_type,
        date_to: date_type,
    ) -> None:
        """Reject if a live booking or hold already occupies the range.

        `HoldService.place` re-checks holds on its own, but it never looks at
        bookings — so this is the only place the booking-occupancy half of the
        guard runs.
        """
        if Booking.objects.occupying(
            property=property, date_from=date_from, date_to=date_to
        ).exists():
            raise OverlappingBooking(
                f"A booking already occupies {date_from}..{date_to} on property {property.pk}"
            )

    @classmethod
    @transaction.atomic
    def create(
        cls,
        *,
        property: Property,
        created_by: User,
        date_from: date_type,
        date_to: date_type,
        kind: str = OwnerBlockKind.OWNER_STAY.value,
        notes: str = "",
    ) -> OwnerBlock:
        """Submit a PENDING block request after an immediate-feedback overlap check.

        The submit-time check is advisory feedback for the owner; the
        authoritative check runs again at approval, since the pending request
        reserves nothing in the meantime.
        """
        cls._assert_range_free(property=property, date_from=date_from, date_to=date_to)
        if BookingHold.live_overlapping(
            property=property, date_from=date_from, date_to=date_to
        ).exists():
            raise HoldUnavailable(
                f"An overlapping live hold already exists for property "
                f"{property.pk} on {date_from}..{date_to}"
            )
        return OwnerBlock.objects.create(
            property=property,
            created_by=created_by,
            date_from=date_from,
            date_to=date_to,
            kind=kind,
            notes=notes,
            status=OwnerBlockStatus.PENDING.value,
        )

    @staticmethod
    def _guard_pending(request: OwnerBlock, *, to: str) -> None:
        if request.status != OwnerBlockStatus.PENDING.value:
            raise InvalidTransition(request.status, to, allowed=[OwnerBlockStatus.PENDING.value])

    @classmethod
    @transaction.atomic
    def approve(
        cls,
        request: OwnerBlock,
        *,
        actor: User | None = None,
        review_note: str = "",
    ) -> OwnerBlock:
        """Approve a PENDING request: place the indefinite hold, mark APPROVED.

        Re-runs the full overlap guard — this is the authoritative check. A
        late-arriving *hold* conflict surfaces as `HoldUnavailable` from
        `HoldService.place`; a *booking* conflict as `OverlappingBooking` here.
        """
        cls._guard_pending(request, to=OwnerBlockStatus.APPROVED.value)
        cls._assert_range_free(
            property=request.property,
            date_from=request.date_from,
            date_to=request.date_to,
        )
        hold = HoldService.place(
            property=request.property,
            date_from=request.date_from,
            date_to=request.date_to,
            never_expires=True,
            reason=_KIND_TO_HOLD_REASON.get(request.kind, _DEFAULT_HOLD_REASON),
            notes=request.notes,
        )
        request.status = OwnerBlockStatus.APPROVED.value
        request.resulting_hold = hold
        request.reviewed_by = actor
        request.reviewed_at = timezone.now()
        request.review_note = review_note
        request.save(
            update_fields=[
                "status",
                "resulting_hold",
                "reviewed_by",
                "reviewed_at",
                "review_note",
                "updated_at",
            ]
        )
        return request

    @classmethod
    @transaction.atomic
    def decline(
        cls,
        request: OwnerBlock,
        review_note: str,
        *,
        actor: User | None = None,
    ) -> OwnerBlock:
        """Decline a PENDING request. No hold is created."""
        cls._guard_pending(request, to=OwnerBlockStatus.DECLINED.value)
        request.status = OwnerBlockStatus.DECLINED.value
        request.reviewed_by = actor
        request.reviewed_at = timezone.now()
        request.review_note = review_note
        request.save(
            update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"]
        )
        return request

    @classmethod
    @transaction.atomic
    def cancel(
        cls,
        request: OwnerBlock,
        *,
        actor: User | None = None,
    ) -> OwnerBlock:
        """Owner-initiated cancel.

        PENDING → CANCELLED (nothing else to undo). APPROVED → release the
        resulting hold (freeing the calendar) then CANCELLED. A request in a
        terminal state (DECLINED/CANCELLED) is rejected.
        """
        if request.status not in (
            OwnerBlockStatus.PENDING.value,
            OwnerBlockStatus.APPROVED.value,
        ):
            raise InvalidTransition(
                request.status,
                OwnerBlockStatus.CANCELLED.value,
                allowed=[
                    OwnerBlockStatus.PENDING.value,
                    OwnerBlockStatus.APPROVED.value,
                ],
            )
        if request.resulting_hold_id is not None and request.resulting_hold is not None:
            HoldService.release(request.resulting_hold)
        request.status = OwnerBlockStatus.CANCELLED.value
        request.reviewed_by = actor
        request.reviewed_at = timezone.now()
        request.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
        return request
