"""Enquiry, EnquiryNote, EnquiryEvent — the lead-capture cluster."""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import models, transaction

from core.exceptions import InvalidTransition
from core.fields import CIEmailField
from core.models.base import AuditedModel, TimestampedModel
from core.refs import generate_reference
from reservations.enums import (
    EnquiryEventKind,
    EnquiryNoteKind,
    EnquiryRequestType,
    EnquirySource,
    EnquiryStatus,
    EventSource,
    QuotationStatus,
)

if TYPE_CHECKING:
    from reservations.models.quotation import Quotation


class Enquiry(AuditedModel):
    """Inbound lead — anonymous form, agent, phone, email."""

    reference = models.CharField(max_length=32, unique=True)
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

    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    is_flexible = models.BooleanField(default=False)
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
        "accounts.Contact",
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
    inbound_message = models.TextField(blank=True)

    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["email"]),
            models.Index(fields=["property", "date_from"]),
        ]
        ordering = ["-created_at"]
        verbose_name_plural = "enquiries"

    def __str__(self) -> str:
        return self.reference

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.reference:
            self.reference = generate_reference("E", model=type(self))
        super().save(*args, **kwargs)

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
        """
        return self.quotations.filter(status=QuotationStatus.ACCEPTED.value).exists()

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
    ) -> None:
        if self.status not in allowed_from:
            raise InvalidTransition(self.status, to, allowed=list(allowed_from))
        with transaction.atomic():
            prev = self.status
            self.status = to
            self.save(update_fields=["status", "updated_at"])
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
        """Mark this enquiry as contacted (operator reached out)."""
        self._transition(
            allowed_from=(EnquiryStatus.NEW.value,),
            to=EnquiryStatus.CONTACTED.value,
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
            allowed_from=(EnquiryStatus.NEW.value, EnquiryStatus.CONTACTED.value),
            to=EnquiryStatus.QUOTED.value,
            kind=EnquiryEventKind.QUOTE_SENT.value,
            actor=actor,
            meta=event_meta,
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

    def convert(self, quotation: Quotation, *, actor: Any = None) -> Enquiry:
        """Mark this enquiry as converted (a booking was made from a quotation)."""
        self._transition(
            allowed_from=(EnquiryStatus.QUOTED.value, EnquiryStatus.CONTACTED.value),
            to=EnquiryStatus.CONVERTED.value,
            kind=EnquiryEventKind.CONVERTED.value,
            actor=actor,
            meta={"quotation_id": quotation.pk},
        )
        return self

    def lose(self, reason: str = "", *, actor: Any = None) -> Enquiry:
        """Mark as lost; reachable from any non-converted state."""
        self._transition(
            allowed_from=(
                EnquiryStatus.NEW.value,
                EnquiryStatus.CONTACTED.value,
                EnquiryStatus.QUOTED.value,
            ),
            to=EnquiryStatus.LOST.value,
            kind=EnquiryEventKind.LOST.value,
            actor=actor,
            reason=reason,
        )
        return self

    def reopen(self, *, actor: Any = None, reason: str = "") -> Enquiry:
        """Bring a LOST enquiry back to NEW for renewed work."""
        self._transition(
            allowed_from=(EnquiryStatus.LOST.value,),
            to=EnquiryStatus.NEW.value,
            kind=EnquiryEventKind.REOPENED.value,
            actor=actor,
            reason=reason,
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
