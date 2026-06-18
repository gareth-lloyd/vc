"""Reservations app signals.

Defines:
- `booking_transitioned` — fired by every Booking state-machine transition.
- `hold_expired` — fired per BookingHold row that the `expire_holds` task
  has just released past its `expires_at`.

Wires up:
- `EnquiryNote` post_save → emit a `NOTE_ADDED` `EnquiryEvent`.
- `BookingConciergeItem` post_save / post_delete → recompute
  `Booking.adjustment` from non-cancelled concierge items.
"""

from __future__ import annotations

from typing import Any

from django.db.models import ProtectedError
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import Signal

from reservations.enums import (
    BookingGuestRole,
    EnquiryEventKind,
    EventSource,
)

# ---------------------------------------------------------------------------
# Public signals
# ---------------------------------------------------------------------------

booking_transitioned = Signal()
"""Fired on every Booking state machine transition.

kwargs: sender=Booking, booking, from_status, to_status, actor, source.
"""

hold_expired = Signal()
"""Fired once per BookingHold released by the `expire_holds` Celery task.

kwargs: sender=BookingHold, hold.
"""

quotation_sent = Signal()
"""Fired by `Quotation.send()` on the DRAFT → SENT transition.

kwargs: sender=Quotation, quotation.
"""

owner_block_contested = Signal()
"""Fired by `OwnerBlockService.contest` when staff dispute an owner block.

The block stays APPROVED (the hold is untouched) — the signal exists only to
notify the owner. comms listens and emails the property's primary owner.

kwargs: sender=OwnerBlock, block, actor, reason.
"""

ical_conflict_detected = Signal()
"""Fired by the iCal poller when an imported busy range clashes with a live VC commitment.

The poller skips writing the conflicting block (the VC commitment stands) and
fires this so comms can alert ops. Two clash kinds escalate: an imported range
overlapping a confirmed booking, or one overlapping an open-quotation hold (VC is
quoting dates the owner just booked on their other channel). Benign owner-side
holds (manual block / maintenance) and routine non-conflicting imports do not fire
it; the latter go to the OwnerBlockUpdate awareness feed only.

kwargs: sender=None, property, date_from, date_to, conflict_kind ("booking" /
"quotation"), conflict_reference (booking/quotation ref), booking (the clashing
Booking for the booking kind, else None), feed_labels (provenance).
"""

booking_total_changed = Signal()
"""Fired when staff-entered money changes what the guest owes on a booking.

Today that means a `BookingChargeItem` create/update/delete. payments
listens and resizes the unsettled DEPOSIT/BALANCE schedule rows
(`PaymentScheduler.resync_for_booking`) — the signal exists because the
import spine forbids reservations importing payments.

Sent from model signal handlers (not just the service layer) so direct
ORM writes — loaders, shell fixes — still trigger the resync.

kwargs: sender=Booking, booking.
"""

booking_confirmation_resend_requested = Signal()
"""Fired by `Booking.send_confirmation_email()` when an operator triggers a resend.

Decoupled from `booking_transitioned` because no transition occurs — the
booking stays in its current status while a fresh confirmation email goes
out. The comms app listens and dispatches via `EmailService.resend` against
the most recent `booking.confirmation` EmailLog, falling back to a fresh
send when no prior log exists.

kwargs: sender=Booking, booking, actor.
"""


# ---------------------------------------------------------------------------
# EnquiryNote → EnquiryEvent (NOTE_ADDED)
# ---------------------------------------------------------------------------


def _enquiry_note_post_save(
    sender: type,
    instance: Any,
    created: bool,
    **_: Any,
) -> None:
    if not created:
        return
    # Local imports to avoid AppConfig import-order issues.
    from reservations.models.enquiry import EnquiryEvent

    EnquiryEvent.objects.create(
        enquiry=instance.enquiry,
        from_status=instance.enquiry.status,
        to_status=instance.enquiry.status,
        kind=EnquiryEventKind.NOTE_ADDED.value,
        actor=instance.author,
        source=EventSource.USER.value,
        meta={"note_id": instance.pk, "kind": instance.kind},
    )


# ---------------------------------------------------------------------------
# BookingConciergeItem → Booking.adjustment recompute
# ---------------------------------------------------------------------------


def _concierge_item_changed(sender: type, instance: Any, **_: Any) -> None:
    # Single-row save/delete only. Bulk concierge writes (queryset.update(),
    # bulk_create, bulk_update) fire no signal and so silently desync
    # Booking.adjustment — they must call ConciergeService.recompute_adjustment
    # (or .recompute_for_bookings) explicitly (FG-011; same bulk-write/signal
    # blind spot as the AuditLog convention in django_res/CLAUDE.md).
    from reservations.services.concierge import ConciergeService

    ConciergeService.recompute_adjustment(instance.booking_id)


# ---------------------------------------------------------------------------
# BookingChargeItem → booking_total_changed
# ---------------------------------------------------------------------------


def _charge_item_changed(sender: type, instance: Any, **_: Any) -> None:
    from reservations.models.booking import Booking

    booking_total_changed.send(sender=Booking, booking=instance.booking)


# ---------------------------------------------------------------------------
# BookingGuest(role=LEAD) → Booking.guest sync
# ---------------------------------------------------------------------------


def _booking_guest_post_save(sender: type, instance: Any, **_: Any) -> None:
    """Mirror the LEAD BookingGuest row onto `Booking.guest`.

    `Booking.guest` survives as a denormalised pointer so the many
    booking-list / search reads that touch `guest_id` don't have to
    refactor through the through-table. The LEAD row is the source of
    truth; this signal keeps the denormalised column in sync.

    The write goes through a queryset `.update()` (not `instance.save()`)
    on purpose:

    - It bypasses `Booking.save()` and the `updated_at` `auto_now` bump,
      so the canonical audit trail for "who is the LEAD guest" stays on
      `BookingGuest` (which is `core.audit.track`'d) instead of muddying
      the Booking's audit timeline with denorm-sync writes.
    - Queryset `.update()` fires no `post_save`, so there is no
      recursion risk back into this handler via `Booking` signals.
    - It is a single UPDATE statement with no read-modify-write, so it
      stays cheap on hot booking-list paths.
    """
    if instance.role != BookingGuestRole.LEAD.value:
        return
    from reservations.models.booking import Booking

    # Intentional queryset .update() — denorm sync of Booking.guest only.
    # Skips Booking.save() (and its auto_now updated_at bump) so the canonical
    # audit trail stays on BookingGuest. Also: queryset .update() fires no
    # post_save, so no recursion risk.
    Booking.objects.filter(pk=instance.booking_id).exclude(guest_id=instance.guest_id).update(
        guest_id=instance.guest_id,
    )


# ---------------------------------------------------------------------------
# Guest → Person mirror (GAP-045 Unit 3c)
# ---------------------------------------------------------------------------


def _guest_post_save(
    sender: type,
    instance: Any,
    update_fields: frozenset[str] | None = None,
    **_: Any,
) -> None:
    """Keep the unified `accounts.Person` mirror in sync with every Guest write.

    The mirror lets Unit 3c switch reads/FKs onto Person while Guest is still the
    write surface; both go away when Guest is retired (Unit 3d). A targeted save
    that touches none of the synced fields (e.g. a denorm-only column) is skipped.
    """
    from reservations.services.person_sync import SYNCED_GUEST_FIELDS, sync_person_from_guest

    if update_fields is not None and SYNCED_GUEST_FIELDS.isdisjoint(update_fields):
        return
    sync_person_from_guest(instance)


# ---------------------------------------------------------------------------
# BookingGuest(role=LEAD) → orphan-guard on delete
# ---------------------------------------------------------------------------


class LeadGuestProtectedError(ProtectedError):
    """Raised when deleting a LEAD `BookingGuest` would orphan a live Booking.

    A `Booking` invariant is "exactly one LEAD guest". The partial unique
    constraint `bookingguest_one_lead_per_booking` blocks the "create new
    LEAD first" swap pattern, so callers must instead demote the old LEAD
    (e.g. set its `role` to CO_TRAVELLER) and create the new LEAD row in
    the same `transaction.atomic()` block. Then the old row can be deleted
    safely if desired, because it is no longer the LEAD.
    """


def _booking_guest_pre_delete(
    sender: type,
    instance: Any,
    origin: Any | None = None,
    **_: Any,
) -> None:
    """Refuse to delete a LEAD row while its Booking still exists.

    Allowed:
    - The parent `Booking` is being deleted in the same statement (CASCADE
      path). We detect this via the `origin` kwarg that
      `Collector.delete()` passes to `pre_delete`: when the deletion was
      triggered by `Booking.delete()` (or a queryset delete that includes
      the Booking), `origin` is the Booking instance, not the BookingGuest
      itself. A direct `bookingguest.delete()` call sets `origin` to the
      BookingGuest row itself.
    - Non-LEAD rows (CO_TRAVELLER, PAYER, CC_ONLY): deleting them never
      breaks the "one LEAD per booking" invariant.

    Refused:
    - Direct deletion of a LEAD row while its Booking still exists.

    The recommended swap pattern is *demote, then re-add*: inside one
    `transaction.atomic()` block, `.update()` the existing LEAD row's
    `role` away from LEAD (e.g. to CO_TRAVELLER) and create the new LEAD
    row. The "create new LEAD first" pattern is blocked by the partial
    unique constraint, so demotion is the only workable path.
    """
    if instance.role != BookingGuestRole.LEAD.value:
        return

    # Cascade detection — `origin` is the row whose .delete() / queryset
    # delete kicked off the collector walk. If it isn't the BookingGuest
    # row itself, the deletion is a cascade from a parent (Booking or
    # Guest) and the "one LEAD per booking" invariant can't be violated:
    # either the parent Booking is going too, or PROTECT on the Guest FK
    # would have blocked the parent delete before we got here.
    if origin is not None and origin is not instance:
        return

    raise LeadGuestProtectedError(
        "Cannot delete the LEAD BookingGuest while its Booking still exists. "
        "Demote the existing LEAD row (e.g. set role=CO_TRAVELLER) and create "
        "the replacement LEAD row in the same transaction instead.",
        {instance},
    )


def _quotation_line_pre_delete(sender: type, instance: Any, **_: Any) -> None:
    """Release a deleted quotation line's live holds so its dates free up.

    Lives at the model layer (not just the API viewset) so the invariant
    holds for *every* delete path — the line-CRUD endpoint, a direct ORM
    `delete()`, seeding, or a cascade from deleting the parent Quotation.
    Without this, a line removed outside the viewset would leave a live
    `QUOTATION_OPEN` hold blocking the calendar indefinitely.
    """
    from reservations.services.holds import HoldService

    HoldService.release_for_line(instance)


# ---------------------------------------------------------------------------
# Registration — bound on import (apps.py ready() imports this module)
# ---------------------------------------------------------------------------


def _connect() -> None:
    from reservations.models.booking_guest import BookingGuest
    from reservations.models.charge_item import BookingChargeItem
    from reservations.models.concierge import BookingConciergeItem
    from reservations.models.enquiry import EnquiryNote
    from reservations.models.guest import Guest
    from reservations.models.quotation import QuotationLine

    post_save.connect(
        _enquiry_note_post_save,
        sender=EnquiryNote,
        dispatch_uid="reservations.enquiry_note_post_save",
    )
    post_save.connect(
        _charge_item_changed,
        sender=BookingChargeItem,
        dispatch_uid="reservations.charge_item_post_save",
    )
    post_delete.connect(
        _charge_item_changed,
        sender=BookingChargeItem,
        dispatch_uid="reservations.charge_item_post_delete",
    )
    post_save.connect(
        _concierge_item_changed,
        sender=BookingConciergeItem,
        dispatch_uid="reservations.concierge_item_post_save",
    )
    post_delete.connect(
        _concierge_item_changed,
        sender=BookingConciergeItem,
        dispatch_uid="reservations.concierge_item_post_delete",
    )
    post_save.connect(
        _booking_guest_post_save,
        sender=BookingGuest,
        dispatch_uid="reservations.booking_guest_post_save",
    )
    post_save.connect(
        _guest_post_save,
        sender=Guest,
        dispatch_uid="reservations.guest_post_save",
    )
    pre_delete.connect(
        _booking_guest_pre_delete,
        sender=BookingGuest,
        dispatch_uid="reservations.booking_guest_pre_delete",
    )
    pre_delete.connect(
        _quotation_line_pre_delete,
        sender=QuotationLine,
        dispatch_uid="reservations.quotation_line_pre_delete",
    )


_connect()


__all__ = [
    "LeadGuestProtectedError",
    "booking_total_changed",
    "booking_transitioned",
    "hold_expired",
    "ical_conflict_detected",
    "owner_block_contested",
    "quotation_sent",
]
