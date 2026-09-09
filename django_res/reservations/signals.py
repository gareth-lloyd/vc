"""Reservations app signals.

Defines:
- `booking_transitioned` — fired by every Booking state-machine transition.
- `hold_expired` — fired per BookingHold row that the `expire_holds` task
  has just released past its `expires_at`.

Wires up:
- `EnquiryNote` post_save → emit a `NOTE_ADDED` `EnquiryEvent`.
- `BookingChargeItem` post_save / post_delete → `booking_total_changed`
  (concierge items deliberately do NOT participate — concierge money is
  non-scheduling, SMELL-020; see `reservations/services/concierge.py`).
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import ProtectedError
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import Signal

from core.storage import release_stored_file_after_commit
from reservations.enums import (
    BookingGuestRole,
    BookingStatus,
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
booking_document_send_requested = Signal()
"""Fired when a generated `BookingDocument` should be emailed to the guest.

Auto-generation at confirmation fires it, and so does the staff `:send`
action. comms listens and sends (or resends) the `booking.contract` email with
the document attached — `reservations` cannot import `comms` (upward edge), so
delivery is a receiver on the other side of this signal.

kwargs: sender=BookingDocument, document, actor.
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
# EnquiryNote → Zoho enquiry re-push (GAP-081)
# ---------------------------------------------------------------------------


def _enquiry_note_zoho_bump(sender: type, instance: Any, **_: Any) -> None:
    """Note rows ride the nested notes endpoint without touching the Enquiry
    row, yet push inside the enquiry payload's `notes` list — so a note
    save/delete must bump the parent's Zoho push itself (GAP-081)."""
    from integrations.services.zoho_flow import enqueue_zoho_push, push_suppressed, webhook_url
    from reservations.models.enquiry import Enquiry

    # Guard before the parent deref — bulk cascades under suppression
    # (loaders) or with the webhook unset (dev) shouldn't pay the SELECT.
    if push_suppressed() or not webhook_url("enquiry"):
        return
    try:
        enquiry = instance.enquiry
    except Enquiry.DoesNotExist:
        # Cascade delete mid-flight (parent row already gone) — the reaper
        # clears the parent's own records.
        return
    enqueue_zoho_push(enquiry)


# ---------------------------------------------------------------------------
# BookingChargeItem → booking_total_changed
# ---------------------------------------------------------------------------


def _charge_item_changed(sender: type, instance: Any, **_: Any) -> None:
    from reservations.models.booking import Booking

    booking_total_changed.send(sender=Booking, booking=instance.booking)


# ---------------------------------------------------------------------------
# BookingGuest(role=LEAD) → Booking.person sync
# ---------------------------------------------------------------------------


def _booking_guest_post_save(sender: type, instance: Any, **_: Any) -> None:
    """Mirror the LEAD BookingGuest row onto `Booking.person`.

    `Booking.person` is a denormalised pointer so the many booking-list /
    search reads that touch `person_id` don't have to refactor through the
    through-table. The LEAD row is the source of truth; this signal keeps the
    denormalised column in sync.

    GAP-045 Unit 3d-C: only the unified `person` FK is mirrored — the LEAD
    BookingGuest is created with `person` set (BookingService / factory /
    loader), and the legacy `guest` leg is no longer persisted by any writer.

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

    # Intentional queryset .update() — denorm sync of Booking.person.
    # Skips Booking.save() (and its auto_now updated_at bump) so the canonical
    # audit trail stays on BookingGuest. Also: queryset .update() fires no
    # post_save, so no recursion risk.
    #
    # GAP-045 Unit 3d-C: only the unified `person` denorm column is synced now —
    # the legacy `guest` leg is no longer persisted by any writer. The cheap-skip
    # excludes the row when `person_id` already matches, so an already-synced
    # booking costs one no-op UPDATE (zero rows).
    Booking.objects.filter(pk=instance.booking_id).exclude(person_id=instance.person_id).update(
        person_id=instance.person_id
    )

    # GAP-082: the denorm sync above is a queryset .update() — no Booking
    # post_save — yet a LEAD change rewrites the booking payload's `person`,
    # so the re-push must ride this receiver. Guard before the booking deref
    # (this handler fires on every LEAD BookingGuest save).
    from integrations.services.zoho_flow import enqueue_zoho_push, push_suppressed, webhook_url

    if push_suppressed() or not webhook_url("booking"):
        return
    try:
        booking = instance.booking
    except Booking.DoesNotExist:
        return
    enqueue_zoho_push(booking)


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
# Booking confirmed → auto-generate the contract (GAP-094)
# ---------------------------------------------------------------------------


def _booking_confirmed_generate_contract(
    sender: type,
    booking: Any,
    to_status: str,
    **_: Any,
) -> None:
    """Schedule contract generation when a booking enters AWAITING_DEPOSIT.

    Deferred to `on_commit` so the PDF render (and the email it triggers)
    never happens against a transaction that might still roll back, and so a
    slow render can't extend the transaction holding the booking's row lock.
    """
    if to_status != BookingStatus.AWAITING_DEPOSIT.value:
        return

    from reservations.services.booking_documents import auto_generate_contract

    booking_pk = booking.pk
    transaction.on_commit(lambda: auto_generate_contract(booking_pk))


# ---------------------------------------------------------------------------
# Registration — bound on import (apps.py ready() imports this module)
# ---------------------------------------------------------------------------


def _release_booking_document_blob(sender: Any, instance: Any, **kwargs: Any) -> None:
    """Release a deleted `BookingDocument`'s PDF once the delete commits.

    Registered on `post_delete` rather than done in the service so every
    hard delete releases the bytes — the API `DELETE`, a booking cascade (the
    demo seeder hard-deletes bookings), admin, shell — and guest-PII PDFs do
    not accumulate in the private bucket with nothing pointing at them.
    """
    release_stored_file_after_commit(
        instance.file,
        log_event="reservations.booking_document_blob_orphaned",
        booking_id=instance.booking_id,
        document_id=instance.pk,
    )


def _connect() -> None:
    from reservations.models.booking_document import BookingDocument
    from reservations.models.booking_guest import BookingGuest
    from reservations.models.charge_item import BookingChargeItem
    from reservations.models.enquiry import EnquiryNote
    from reservations.models.quotation import QuotationLine

    post_save.connect(
        _enquiry_note_post_save,
        sender=EnquiryNote,
        dispatch_uid="reservations.enquiry_note_post_save",
    )
    post_save.connect(
        _enquiry_note_zoho_bump,
        sender=EnquiryNote,
        dispatch_uid="reservations.enquiry_note_zoho_bump_post_save",
    )
    post_delete.connect(
        _enquiry_note_zoho_bump,
        sender=EnquiryNote,
        dispatch_uid="reservations.enquiry_note_zoho_bump_post_delete",
    )
    post_delete.connect(
        _release_booking_document_blob,
        sender=BookingDocument,
        dispatch_uid="reservations.booking_document_release_blob",
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
        _booking_guest_post_save,
        sender=BookingGuest,
        dispatch_uid="reservations.booking_guest_post_save",
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
    booking_transitioned.connect(
        _booking_confirmed_generate_contract,
        dispatch_uid="reservations.booking_confirmed_generate_contract",
    )


_connect()


__all__ = [
    "LeadGuestProtectedError",
    "booking_confirmation_resend_requested",
    "booking_document_send_requested",
    "booking_total_changed",
    "booking_transitioned",
    "hold_expired",
    "ical_conflict_detected",
    "owner_block_contested",
    "quotation_sent",
]
