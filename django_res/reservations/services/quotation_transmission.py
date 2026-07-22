"""Quotation transmission — the two-send-path side-effect helper.

Per `workflows/08-quotation/transmission.md` "Django redesign — two send paths":

The in-app SMTP send and the operator's "I sent this manually" confirmation both
must produce the same downstream state writes. This module is the single source
of truth for those writes.

Side effects (in a single `transaction.atomic` block):
- `Quotation.status = SENT` (idempotent — already-SENT quotations short-circuit).
- `Enquiry.status = QUOTED` when the enquiry is in NEW/CONTACTED; otherwise the
  status flip is skipped (already further along) but an `EnquiryEvent` is still
  written so the send_path audit is intact.
- `EnquiryEvent(kind=QUOTE_SENT, meta={"send_path": ..., "quotation_id": ...})`.
- `SyncRecord(provider=ZOHO_CRM, status=PENDING)` queued for the Zoho beat task.

Email dispatch is NOT this helper's responsibility — the SMTP path fires the
`quotation_sent` signal, which `comms.signals.quotation_sent_handler` listens to
and turns into the `EmailLog` row. The manual path skips the signal entirely.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from core.exceptions import InvalidTransition
from core.locking import refresh_locked
from reservations.enums import (
    EnquiryEventKind,
    EnquiryStatus,
    EventSource,
    QuotationStatus,
)

if TYPE_CHECKING:
    from reservations.models.quotation import Quotation


# Send-path tags — these strings are persisted on `EnquiryEvent.meta` and read
# by reporting queries. Treat them as a closed set.
SEND_PATH_SMTP = "smtp"
SEND_PATH_MANUAL = "manual"
_VALID_SEND_PATHS = frozenset({SEND_PATH_SMTP, SEND_PATH_MANUAL})


@transaction.atomic
def record_quote_sent(
    quotation: Quotation,
    *,
    send_path: str,
    actor: Any = None,
) -> Quotation:
    """Apply post-send state writes for a Quotation.

    Idempotent on state: if the quotation is already SENT the status flip is
    skipped, but a re-send still records its audit event (per send_path) and
    re-enqueues the Zoho push — a re-send IS a send (GAP-081). Otherwise
    enforces DRAFT → SENT and writes the downstream state.

    Raises `InvalidTransition` if the quotation is in a non-DRAFT, non-SENT
    state (ACCEPTED, EXPIRED, CANCELLED) — those are terminal/diverged and
    re-marking them as SENT would corrupt the audit trail.
    """
    if send_path not in _VALID_SEND_PATHS:
        raise ValueError(
            f"send_path must be one of {sorted(_VALID_SEND_PATHS)!r}, got {send_path!r}"
        )

    # Lock + re-read so concurrent sends serialise: the loser re-reads SENT
    # and takes the idempotency short-circuit instead of re-flipping state.
    refresh_locked(quotation)

    # Idempotency short-circuit — re-POST on an already-SENT quote skips the
    # status flip only. The audit event is gated by the (quotation,
    # send_path) pair: if the operator confirms a manual re-send after an
    # SMTP send (because they suspect the email never arrived), the manual
    # confirmation still has to land on the audit trail. The Zoho push IS
    # deliberately re-enqueued (GAP-081): SENT is an editable, re-sendable
    # status (renegotiation) and the re-send delivers the updated email —
    # the CRM must get the updated payload too. Safe: idempotent PENDING
    # upsert, payload built at push time.
    if quotation.status == QuotationStatus.SENT.value:
        enquiry = quotation.enquiry
        if enquiry is not None:
            _record_audit_event_if_new_path(
                enquiry=enquiry,
                quotation=quotation,
                send_path=send_path,
                actor=actor,
            )
        _queue_zoho_push(quotation)
        return quotation

    if quotation.status != QuotationStatus.DRAFT.value:
        raise InvalidTransition(
            quotation.status,
            QuotationStatus.SENT.value,
            allowed=[QuotationStatus.DRAFT.value],
        )

    # 1. Flip the quotation.
    quotation.status = QuotationStatus.SENT.value
    update_fields = ["status", "updated_at"]
    if quotation.expires_at is None:
        quotation.expires_at = timezone.now() + timedelta(days=7)
        update_fields.append("expires_at")
    quotation.save(update_fields=update_fields)

    # 2. Enquiry status + audit event.
    enquiry = quotation.enquiry
    if enquiry is not None:
        _record_enquiry_quote_sent(
            enquiry=enquiry,
            quotation=quotation,
            send_path=send_path,
            actor=actor,
        )

    # 3. Queue the Zoho push.
    _queue_zoho_push(quotation)

    return quotation


def _record_enquiry_quote_sent(
    *,
    enquiry: Any,
    quotation: Quotation,
    send_path: str,
    actor: Any,
) -> None:
    """Flip enquiry → QUOTE_SENT if it's in a pre-quote state; always write event."""
    transitionable_from = (
        EnquiryStatus.NEW.value,
        EnquiryStatus.PROGRESSING.value,
        EnquiryStatus.FOLLOW_UP.value,
    )

    if enquiry.status in transitionable_from:
        # `enquiry.quote_sent` runs the transition + writes the EnquiryEvent
        # inside its own `transaction.atomic` block; the wrapping atomic on
        # `record_quote_sent` keeps the whole thing one savepoint.
        enquiry.quote_sent(quotation, send_path=send_path, actor=actor)
        return

    # Enquiry already QUOTED/CONVERTED/LOST — don't transition, but the
    # send_path audit still has to land.
    _record_audit_event_if_new_path(
        enquiry=enquiry,
        quotation=quotation,
        send_path=send_path,
        actor=actor,
    )


def _record_audit_event_if_new_path(
    *,
    enquiry: Any,
    quotation: Quotation,
    send_path: str,
    actor: Any,
) -> None:
    """Write an EnquiryEvent(kind=QUOTE_SENT) iff no event already exists for
    the (quotation, send_path) pair.

    Covers two non-transitioning cases:

    1. The enquiry is already QUOTED/CONVERTED/LOST when `record_quote_sent`
       runs — we still want the send_path audit, just not a status flip.
    2. The quotation is already SENT (the idempotency short-circuit) but the
       operator is recording a *different* send_path — e.g. manual-mark
       after a prior SMTP send. We MUST land the new audit row; dropping
       it would silently erase the operator's confirmation.

    Skips when a prior event with the same (quotation, send_path) already
    exists — covers double-clicks and signal-driven double-fires.
    """
    from reservations.models.enquiry import EnquiryEvent

    duplicate = EnquiryEvent.objects.filter(
        enquiry=enquiry,
        kind=EnquiryEventKind.QUOTE_SENT.value,
        meta__quotation_id=quotation.pk,
        meta__send_path=send_path,
    ).exists()
    if duplicate:
        return

    EnquiryEvent.objects.create(
        enquiry=enquiry,
        from_status=enquiry.status,
        to_status=enquiry.status,
        kind=EnquiryEventKind.QUOTE_SENT.value,
        actor=actor,
        source=EventSource.USER.value,
        meta={"quotation_id": quotation.pk, "send_path": send_path},
    )


def _queue_zoho_push(quotation: Quotation) -> None:
    """Queue the Zoho Flow push for a just-sent quotation (GAP-081).

    Delegates to `enqueue_zoho_push`, which owns the whole contract: the
    PENDING `SyncRecord` upsert, `transaction.on_commit` dispatch of the
    delivery task, loader suppression, and the URL-unset full no-op (unset
    webhook = push disabled entirely, the dev default).
    """
    # Local import keeps the integrations dependency lazy at call time,
    # matching the rest of this module's cross-app import style.
    from integrations.services.zoho_flow import enqueue_zoho_push

    enqueue_zoho_push(quotation)
