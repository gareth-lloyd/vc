"""OwnerBlockService — lifecycle for owner availability blocks.

An owner blocking their own villa is not a request to be gate-kept: the block
is created already APPROVED and the real (indefinite) `BookingHold` is placed in
the same transaction, so the calendar is occupied immediately. The overlap check
is therefore authoritative at create time. `HoldService.place` only guards
against overlapping *holds* — no DB constraint spans the bookings↔holds tables —
so the service also rejects when a live booking occupies the range.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from core.exceptions import InvalidTransition, OverlappingBooking
from properties.services import PropertyAvailabilityService
from reservations.enums import (
    BookingHoldReason,
    OwnerBlockKind,
    OwnerBlockSource,
    OwnerBlockStatus,
    OwnerBlockUpdateKind,
)
from reservations.models import (
    Booking,
    OwnerBlock,
    OwnerBlockUpdate,
    OwnerBlockUpdateSeen,
)
from reservations.services.holds import HoldService
from reservations.signals import owner_block_contested

if TYPE_CHECKING:
    from accounts.models import User
    from properties.models import Property

_KIND_TO_HOLD_REASON = {
    OwnerBlockKind.MAINTENANCE.value: BookingHoldReason.MAINTENANCE.value,
}
_DEFAULT_HOLD_REASON = BookingHoldReason.OWNER_BLOCK.value


class OwnerBlockService:
    """Create and cancel owner availability blocks."""

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
        booking = Booking.objects.occupying(
            property=property, date_from=date_from, date_to=date_to
        ).first()
        if booking is not None:
            raise OverlappingBooking(
                f"A booking already occupies {date_from}..{date_to} on property {property.pk}",
                booking=booking,
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
        """Create an APPROVED block and place its indefinite hold up front.

        The overlap guard is authoritative here, since the block occupies the
        calendar the moment it exists. A *hold* conflict surfaces as
        `HoldUnavailable` from `HoldService.place`; a *booking* conflict as
        `OverlappingBooking`.
        """
        cls._assert_range_free(property=property, date_from=date_from, date_to=date_to)
        hold = HoldService.place(
            property=property,
            date_from=date_from,
            date_to=date_to,
            never_expires=True,
            reason=_KIND_TO_HOLD_REASON.get(kind, _DEFAULT_HOLD_REASON),
            notes=notes,
        )
        block = OwnerBlock.objects.create(
            property=property,
            created_by=created_by,
            date_from=date_from,
            date_to=date_to,
            kind=kind,
            notes=notes,
            status=OwnerBlockStatus.APPROVED.value,
            resulting_hold=hold,
        )
        OwnerBlockUpdate.objects.create(
            block=block,
            kind=OwnerBlockUpdateKind.CREATED.value,
            actor=created_by,
        )
        # GAP-033 Signal 1: an owner just changed their availability.
        PropertyAvailabilityService.touch_owner_updated(property)
        return block

    @classmethod
    @transaction.atomic
    def create_imported(
        cls,
        *,
        property: Property,
        date_from: date_type,
        date_to: date_type,
        idempotency_key: str,
        notes: str = "",
    ) -> OwnerBlock:
        """Create an APPROVED block imported from an iCal feed (GAP-011).

        Mirrors `create` but carries no human creator — an automated feed poll
        is the `actor=None` system caller — and records `source=ICAL` plus the
        reconciliation `idempotency_key` (the coalesced date range). The overlap
        guard is identical: a live booking raises `OverlappingBooking` (the
        poller turns this into a staff conflict alert and skips the write); an
        overlapping live hold raises `HoldUnavailable`.
        """
        cls._assert_range_free(property=property, date_from=date_from, date_to=date_to)
        hold = HoldService.place(
            property=property,
            date_from=date_from,
            date_to=date_to,
            never_expires=True,
            reason=_DEFAULT_HOLD_REASON,
            notes=notes,
        )
        block = OwnerBlock.objects.create(
            property=property,
            created_by=None,
            date_from=date_from,
            date_to=date_to,
            kind=OwnerBlockKind.OTHER.value,
            notes=notes,
            status=OwnerBlockStatus.APPROVED.value,
            source=OwnerBlockSource.ICAL.value,
            idempotency_key=idempotency_key,
            resulting_hold=hold,
        )
        OwnerBlockUpdate.objects.create(
            block=block,
            kind=OwnerBlockUpdateKind.CREATED.value,
            actor=None,
        )
        return block

    @classmethod
    @transaction.atomic
    def cancel(
        cls,
        block: OwnerBlock,
        *,
        actor: User | None = None,
    ) -> OwnerBlock:
        """Cancel an APPROVED block: release its hold, mark CANCELLED.

        A block already in a terminal state (CANCELLED) is rejected.
        """
        if block.status != OwnerBlockStatus.APPROVED.value:
            raise InvalidTransition(
                block.status,
                OwnerBlockStatus.CANCELLED.value,
                allowed=[OwnerBlockStatus.APPROVED.value],
            )
        if block.resulting_hold_id is not None and block.resulting_hold is not None:
            HoldService.release(block.resulting_hold)
        block.status = OwnerBlockStatus.CANCELLED.value
        block.save(update_fields=["status", "updated_at"])
        OwnerBlockUpdate.objects.create(
            block=block,
            kind=OwnerBlockUpdateKind.CANCELLED.value,
            actor=actor,
        )
        # GAP-033 Signal 1: only releasing an *owner-sourced* (MANUAL) block is an
        # owner availability change. iCal-driven reconciliation cancels are the
        # feed's churn, surfaced separately as "last calendar import".
        if block.source == OwnerBlockSource.MANUAL.value:
            PropertyAvailabilityService.touch_owner_updated(block.property)
        return block

    @classmethod
    @transaction.atomic
    def contest(
        cls,
        block: OwnerBlock,
        *,
        actor: User,
        reason: str,
    ) -> OwnerBlock:
        """Flag a block as contested and notify the owner; keep it APPROVED.

        Contest disputes the *dates*, not a single feed event — the flag lives
        on the block, so every update row for it surfaces the contested state.
        The block stays APPROVED and the hold is untouched; the only effect is
        the flag plus an `owner_block_contested` signal the comms app turns into
        an email to the property's primary owner.

        Only an APPROVED block can be contested — a CANCELLED block's hold is
        already released, so there is nothing to dispute. Contesting is also
        idempotent: a second call (a double-click, or a second staff member)
        is a no-op that preserves the original disputer and reason, so the owner
        is not re-emailed.
        """
        if not reason.strip():
            raise ValueError("A contest reason is required.")
        if block.status != OwnerBlockStatus.APPROVED.value:
            raise InvalidTransition(
                block.status,
                "contested",
                allowed=[OwnerBlockStatus.APPROVED.value],
            )
        if block.contested_at is not None:
            return block
        block.contested_at = timezone.now()
        block.contested_by = actor
        block.contest_reason = reason
        block.save(update_fields=["contested_at", "contested_by", "contest_reason", "updated_at"])
        owner_block_contested.send(
            sender=OwnerBlock,
            block=block,
            actor=actor,
            reason=reason,
        )
        return block

    @staticmethod
    def mark_seen(update: OwnerBlockUpdate, *, user: User) -> OwnerBlockUpdateSeen:
        """Mark a feed update seen for one staff user (idempotent, per-user)."""
        seen, _ = OwnerBlockUpdateSeen.objects.get_or_create(update=update, user=user)
        return seen
