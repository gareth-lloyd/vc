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

from django.contrib.contenttypes.models import ContentType
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

    Idempotent: if the quotation is already SENT, returns it untouched.
    Otherwise enforces DRAFT → SENT and writes the downstream state.

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
    # status flip and the Zoho push. The audit event, however, is gated by
    # the (quotation, send_path) pair: if the operator confirms a manual
    # re-send after an SMTP send (because they suspect the email never
    # arrived), the manual confirmation still has to land on the audit trail.
    if quotation.status == QuotationStatus.SENT.value:
        enquiry = quotation.enquiry
        if enquiry is not None:
            _record_audit_event_if_new_path(
                enquiry=enquiry,
                quotation=quotation,
                send_path=send_path,
                actor=actor,
            )
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
    """Create / refresh a PENDING `SyncRecord` for the Zoho push.

    Idempotent via the unique `(content_type, object_id, provider)` constraint
    on `SyncRecord` — a second call on the same quotation just bumps an
    existing row back to PENDING.
    """
    # Local imports keep the integrations dependency out of import order
    # for the reservations app (`integrations` imports from reservations
    # nowhere, but the contenttypes lookup is cheap at call time).
    from integrations.enums import SyncDirection, SyncProvider, SyncStatus
    from integrations.models import SyncRecord
    from reservations.models.quotation import Quotation as _QuotationModel

    content_type = ContentType.objects.get_for_model(_QuotationModel)
    record, was_created = SyncRecord.objects.get_or_create(
        content_type=content_type,
        object_id=quotation.pk,
        provider=SyncProvider.ZOHO_CRM.value,
        defaults={
            "direction": SyncDirection.PUSH.value,
            "status": SyncStatus.PENDING.value,
        },
    )
    if not was_created and record.status != SyncStatus.PENDING.value:
        record.status = SyncStatus.PENDING.value
        record.save(update_fields=["status", "updated_at"])
