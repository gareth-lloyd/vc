"""Enquiry, EnquiryNote, EnquiryEvent — the lead-capture cluster."""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models, transaction

from core.exceptions import InvalidTransition
from core.fields import CIEmailField
from core.locking import refresh_locked
from core.models.base import AuditedModel, TimestampedModel
from core.refs import reference_db_default
from reservations.enums import (
    ContactMethod,
    EnquiryEventKind,
    EnquiryLostReason,
    EnquiryNoteKind,
    EnquiryRequestType,
    EnquirySource,
    EnquiryStatus,
    EventSource,
    LeadStatus,
    QuotationStatus,
)

if TYPE_CHECKING:
    from reservations.models.quotation import Quotation


class Enquiry(AuditedModel):
    """Inbound lead — anonymous form, agent, phone, email."""

    reference = models.CharField(
        max_length=32,
        unique=True,
        db_default=reference_db_default("E", sequence="enquiry_reference_seq"),
    )
    guest = models.ForeignKey(
        "reservations.Guest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="enquiries",
    )

    # Denormalised for purely-anonymous submissions until a Guest is captured.
    first_name = models.CharField(max_length=128, blank=True)
    last_name = models.CharField(max_length=128, blank=True)
    email = CIEmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    # Stated preference survives before a Guest exists; carried onto the Guest
    # on resolve. No contactability constraint here — the enquiry is the
    # permissive capture surface; the Guest is the enforced-clean entity.
    contact_method = models.CharField(
        max_length=8,
        choices=ContactMethod.choices,
        null=True,
        blank=True,
    )

    property = models.ForeignKey(
        "properties.Property",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="enquiries",
    )
    region = models.ForeignKey(
        "properties.Region",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="enquiries",
    )

    # date_from / date_to are the client's TRUE requested dates;
    # flexibility_days is the "± N days" spread the quote search widens by.
    # The pair replaces the old destructive form behaviour where the spread
    # was applied to the dates on submit and then discarded.
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    is_flexible = models.BooleanField(default=False)
    flexibility_days = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(3)]
    )
    adults = models.PositiveSmallIntegerField(default=2)
    children = models.PositiveSmallIntegerField(default=0)
    min_bedrooms = models.PositiveSmallIntegerField(null=True, blank=True)

    request_type = models.CharField(
        max_length=16,
        choices=EnquiryRequestType.choices,
        default=EnquiryRequestType.QUOTE,
    )
    referral_code = models.CharField(max_length=64, blank=True)

    agent = models.ForeignKey(
        "accounts.Person",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="enquiries_as_agent",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_enquiries",
    )

    site_source = models.CharField(
        max_length=16,
        choices=EnquirySource.choices,
        default=EnquirySource.MAIN_WEBSITE,
    )
    status = models.CharField(
        max_length=16,
        choices=EnquiryStatus.choices,
        default=EnquiryStatus.NEW,
    )
    # Structured reason a DEAD enquiry was lost. The
    # `enquiry_dead_requires_lost_reason` constraint enforces only one
    # direction — DEAD ⇒ non-empty; non-DEAD rows are left blank by convention
    # (`lose()` sets it, default UNKNOWN; `reopen()` clears it in the same
    # locked UPDATE), not by the DB.
    lost_reason = models.CharField(
        max_length=32,
        choices=EnquiryLostReason.choices,
        blank=True,
        default="",
    )
    # Lead temperature — a subjective sales signal, orthogonal to the workflow
    # `status`. Operator-set via `set_lead_status()` (an inline dropdown in
    # GAP-039); pushed to Zoho as a CRM tag.
    lead_status = models.CharField(
        max_length=8,
        choices=LeadStatus.choices,
        default=LeadStatus.WARM,
    )
    inbound_message = models.TextField(blank=True)

    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["email"]),
            models.Index(fields=["property", "date_from"]),
            models.Index(fields=["lead_status", "status"]),
        ]
        constraints = [
            # A DEAD enquiry must carry a structured lost reason; every other
            # state leaves it blank.
            models.CheckConstraint(
                condition=(~models.Q(status=EnquiryStatus.DEAD) | ~models.Q(lost_reason="")),
                name="enquiry_dead_requires_lost_reason",
            ),
        ]
        ordering = ["-created_at"]
        verbose_name_plural = "enquiries"

    def __str__(self) -> str:
        return self.reference

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------
    # Use `builtins.property` because `property` is shadowed at class body
    # scope by the `property` FK field above.
    @builtins.property
    def is_converted(self) -> bool:
        """Conversion is measured at the Enquiry level (10-decisions.md):
        the enquiry is converted iff any of its quotations is ACCEPTED.

        Reporting that counts conversions must roll up via this property,
        not by counting ACCEPTED `Quotation` rows directly — a single
        enquiry that spawned three quotes (one ACCEPTED, two CANCELLED)
        is one conversion, not three.

        Implementation note: iterate `.quotations.all()` rather than
        applying a fresh `.filter(...).exists()`. The detail-shaped
        `EnquiryViewSet.get_queryset` installs a `prefetch_related` on
        `quotations`; a filtered subquery would bypass that cache and
        re-query on every list row. When the cache is *not* primed (e.g.
        from a service-layer caller or a list endpoint that intentionally
        skipped the prefetch), Django falls back to a single SELECT —
        no worse than the previous behaviour.
        """
        accepted = QuotationStatus.ACCEPTED.value
        return any(q.status == accepted for q in self.quotations.all())

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------
    def _write_event(
        self,
        *,
        from_status: str,
        to_status: str,
        kind: str,
        actor: Any = None,
        source: str = EventSource.USER.value,
        reason: str = "",
        meta: dict[str, Any] | None = None,
    ) -> EnquiryEvent:
        return EnquiryEvent.objects.create(
            enquiry=self,
            from_status=from_status,
            to_status=to_status,
            kind=kind,
            actor=actor,
            source=source,
            reason=reason,
            meta=meta or {},
        )

    def _transition(
        self,
        *,
        allowed_from: tuple[str, ...],
        to: str,
        kind: str,
        actor: Any = None,
        source: str = EventSource.USER.value,
        reason: str = "",
        meta: dict[str, Any] | None = None,
        set_fields: dict[str, Any] | None = None,
    ) -> None:
        with transaction.atomic():
            # Guard against *locked, current* state — a stale instance's
            # in-memory status would let a concurrent double-call both pass
            # and write duplicate events (see core.locking).
            refresh_locked(self)
            if self.status not in allowed_from:
                raise InvalidTransition(self.status, to, allowed=list(allowed_from))
            prev = self.status
            self.status = to
            update_fields = ["status", "updated_at"]
            # `set_fields` are applied *after* the lock-refresh (which discards
            # in-memory changes) so they persist in the same UPDATE as the
            # status change — e.g. lost_reason on lose(), cleared on reopen().
            if set_fields:
                for field, value in set_fields.items():
                    setattr(self, field, value)
                update_fields += list(set_fields)
            self.save(update_fields=update_fields)
            self._write_event(
                from_status=prev,
                to_status=to,
                kind=kind,
                actor=actor,
                source=source,
                reason=reason,
                meta=meta,
            )

    def contact(self, *, actor: Any = None, reason: str = "") -> Enquiry:
        """Move a NEW enquiry to PROGRESSING (operator reached out)."""
        self._transition(
            allowed_from=(EnquiryStatus.NEW.value,),
            to=EnquiryStatus.PROGRESSING.value,
            kind=EnquiryEventKind.CONTACTED.value,
            actor=actor,
            reason=reason,
        )
        return self

    def quote_sent(
        self,
        quotation: Quotation,
        *,
        send_path: str,
        actor: Any = None,
        meta: dict[str, Any] | None = None,
    ) -> Enquiry:
        """Record that a quotation has been issued for this enquiry.

        `send_path` is required — every QUOTE_SENT event must record which
        transmission path (SMTP / manual) it represents so the manual-mark
        endpoint can compute "is this a new audit row or a duplicate?" off
        the (quotation, send_path) pair. See
        `reservations.services.quotation_transmission` for the closed set
        of valid values.

        Callers can pass additional `meta` entries; they are merged on top
        of `{"quotation_id": ..., "send_path": ...}`.
        """
        event_meta: dict[str, Any] = {"quotation_id": quotation.pk, "send_path": send_path}
        if meta:
            event_meta.update(meta)
        self._transition(
            allowed_from=(
                EnquiryStatus.NEW.value,
                EnquiryStatus.PROGRESSING.value,
                EnquiryStatus.FOLLOW_UP.value,
            ),
            to=EnquiryStatus.QUOTE_SENT.value,
            kind=EnquiryEventKind.QUOTE_SENT.value,
            actor=actor,
            meta=event_meta,
        )
        return self

    def follow_up(self, *, actor: Any = None, reason: str = "") -> Enquiry:
        """Operator-set Follow-up: chasing a Progressing / Quote-sent lead (Q2).

        Sending a new quote moves it back to QUOTE_SENT (`quote_sent`), an
        accepted quote converts it (`convert` / `Quotation.accept`), and Close
        marks it DEAD (`lose`).
        """
        self._transition(
            allowed_from=(
                EnquiryStatus.PROGRESSING.value,
                EnquiryStatus.QUOTE_SENT.value,
            ),
            to=EnquiryStatus.FOLLOW_UP.value,
            kind=EnquiryEventKind.FOLLOW_UP.value,
            actor=actor,
            reason=reason,
        )
        return self

    def assign(self, user: Any, *, actor: Any = None) -> Enquiry:
        """Assign an internal staff owner. Non-transitional event."""
        prev_assignee = self.assigned_to_id
        with transaction.atomic():
            self.assigned_to = user
            self.save(update_fields=["assigned_to", "updated_at"])
            self._write_event(
                from_status=self.status,
                to_status=self.status,
                kind=(
                    EnquiryEventKind.UNASSIGNED.value
                    if user is None
                    else EnquiryEventKind.ASSIGNED.value
                ),
                actor=actor,
                meta={
                    "assignee_from": prev_assignee,
                    "assignee_to": user.pk if user is not None else None,
                },
            )
        return self

    def set_lead_status(self, lead_status: str, *, actor: Any = None) -> Enquiry:
        """Set the lead temperature (HOT / WARM / COLD / DEAD).

        Non-transitional: leaves `status` unchanged and writes a
        LEAD_STATUS_CHANGED event (from_status == to_status) carrying the
        temperature change in `meta`. A no-op when the value is unchanged, so
        the activity timeline isn't padded with redundant rows.
        """
        if lead_status not in LeadStatus.values:
            raise ValueError(f"Invalid lead status: {lead_status!r}")
        prev = self.lead_status
        if prev == lead_status:
            return self
        with transaction.atomic():
            self.lead_status = lead_status
            self.save(update_fields=["lead_status", "updated_at"])
            self._write_event(
                from_status=self.status,
                to_status=self.status,
                kind=EnquiryEventKind.LEAD_STATUS_CHANGED.value,
                actor=actor,
                meta={"lead_status_from": prev, "lead_status_to": lead_status},
            )
        return self

    def convert(self, quotation: Quotation, *, actor: Any = None) -> Enquiry:
        """Mark this enquiry as converted (a booking was made from a quotation)."""
        self._transition(
            allowed_from=(
                EnquiryStatus.QUOTE_SENT.value,
                EnquiryStatus.PROGRESSING.value,
                EnquiryStatus.FOLLOW_UP.value,
            ),
            to=EnquiryStatus.CONVERTED.value,
            kind=EnquiryEventKind.CONVERTED.value,
            actor=actor,
            meta={"quotation_id": quotation.pk},
        )
        return self

    def lose(
        self,
        reason: str = "",
        *,
        lost_reason: str = EnquiryLostReason.UNKNOWN.value,
        actor: Any = None,
    ) -> Enquiry:
        """Mark as dead; reachable from any non-converted state.

        `reason` is the free-text note recorded on the event (unchanged).
        `lost_reason` is the structured `EnquiryLostReason` stored on the row;
        it defaults to UNKNOWN so the `enquiry_dead_requires_lost_reason`
        constraint is always satisfied without forcing every caller to choose.
        """
        self._transition(
            allowed_from=(
                EnquiryStatus.NEW.value,
                EnquiryStatus.PROGRESSING.value,
                EnquiryStatus.QUOTE_SENT.value,
                EnquiryStatus.FOLLOW_UP.value,
            ),
            to=EnquiryStatus.DEAD.value,
            kind=EnquiryEventKind.LOST.value,
            actor=actor,
            reason=reason,
            set_fields={"lost_reason": lost_reason},
        )
        return self

    def reopen(self, *, actor: Any = None, reason: str = "") -> Enquiry:
        """Bring a DEAD enquiry back to NEW for renewed work.

        Clears `lost_reason` in the same locked UPDATE as the status change so
        the reopened (non-DEAD) row satisfies the constraint with no window.
        """
        self._transition(
            allowed_from=(EnquiryStatus.DEAD.value,),
            to=EnquiryStatus.NEW.value,
            kind=EnquiryEventKind.REOPENED.value,
            actor=actor,
            reason=reason,
            set_fields={"lost_reason": ""},
        )
        return self


class EnquiryNote(TimestampedModel):
    """Appendable operator note attached to an Enquiry."""

    enquiry = models.ForeignKey(
        Enquiry,
        on_delete=models.CASCADE,
        related_name="notes_collection",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    kind = models.CharField(
        max_length=16,
        choices=EnquiryNoteKind.choices,
        default=EnquiryNoteKind.GENERAL,
    )
    body = models.TextField()
    is_pinned = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["enquiry", "created_at"]),
        ]
        ordering = ["created_at"]


class EnquiryEvent(TimestampedModel):
    """Append-only state-machine + activity audit row."""

    enquiry = models.ForeignKey(
        Enquiry,
        on_delete=models.PROTECT,
        related_name="events",
    )
    from_status = models.CharField(max_length=16, choices=EnquiryStatus.choices)
    to_status = models.CharField(max_length=16, choices=EnquiryStatus.choices)
    kind = models.CharField(max_length=24, choices=EnquiryEventKind.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    source = models.CharField(
        max_length=16,
        choices=EventSource.choices,
        default=EventSource.USER,
    )
    reason = models.CharField(max_length=255, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["enquiry", "created_at"]),
        ]
        ordering = ["created_at"]
