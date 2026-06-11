"""Quotation and QuotationLine."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q

from core.exceptions import InvalidTransition
from core.locking import refresh_locked
from core.models.base import AuditedModel
from core.refs import next_quotation_number, quotation_reference
from reservations.enums import EnquiryStatus, QuotationStatus

# `BookingLoader` back-fills a synthetic Quotation *and* line (`legacy_id`
# prefixed `booking-`) for every imported booking so the legacy quote-history
# walk has a row to hang off. Those are an internal fill artefact and must never
# surface in any operator-facing read — every Quotation/QuotationLine-surfacing
# viewset routes through a `.real()` that drops them (see `django_res/CLAUDE.md`).
SYNTHETIC_LEGACY_PREFIX = "booking-"


class QuotationQuerySet(models.QuerySet["Quotation"]):
    """Quotation queryset with the shared `booking-` synthetic filter."""

    def real(self) -> QuotationQuerySet:
        """Exclude booking-synthesised quotations (see `SYNTHETIC_LEGACY_PREFIX`)."""
        return self.exclude(legacy_id__startswith=SYNTHETIC_LEGACY_PREFIX)


class QuotationLineQuerySet(models.QuerySet["QuotationLine"]):
    """QuotationLine queryset with the shared `booking-` synthetic filter."""

    def real(self) -> QuotationLineQuerySet:
        """Exclude booking-synthesised lines (see `SYNTHETIC_LEGACY_PREFIX`)."""
        return self.exclude(legacy_id__startswith=SYNTHETIC_LEGACY_PREFIX)


class Quotation(AuditedModel):
    """Operator-issued quote — DRAFT → SENT → ACCEPTED / EXPIRED / CANCELLED."""

    objects = QuotationQuerySet.as_manager()

    reference = models.CharField(max_length=32, unique=True)
    number = models.PositiveIntegerField(null=True, blank=True, unique=True)
    enquiry = models.ForeignKey(
        "reservations.Enquiry",
        on_delete=models.PROTECT,
        related_name="quotations",
    )
    guest = models.ForeignKey(
        "reservations.Guest",
        on_delete=models.PROTECT,
        related_name="quotations",
    )
    agent = models.ForeignKey(
        "accounts.Contact",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="quotations_as_agent",
    )
    # No header currency: each line carries its own (GAP-014, legacy parity —
    # `VillaQuotationMaster` had no currency column; a results list freely
    # mixed £/€/$ per line).
    is_unbranded = models.BooleanField(default=False)
    status = models.CharField(
        max_length=16,
        choices=QuotationStatus.choices,
        default=QuotationStatus.DRAFT,
    )
    expires_at = models.DateTimeField()
    terms_version = models.ForeignKey(
        "reservations.TermsVersion",
        on_delete=models.PROTECT,
        related_name="+",
    )
    cancel_reason = models.TextField(blank=True)

    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "expires_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.reference

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.reference:
            # Allocate a sequence-backed number and derive the customer-facing
            # reference (legacy `QVC{number}`). A loader that supplies both
            # `number` and `reference` short-circuits here, preserving exact
            # legacy numbers without drawing from the sequence.
            if self.number is None:
                self.number = next_quotation_number()
            self.reference = quotation_reference(self.number)
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------
    def _assert_from(self, allowed_from: tuple[str, ...], to: str) -> None:
        if self.status not in allowed_from:
            raise InvalidTransition(self.status, to, allowed=list(allowed_from))

    @transaction.atomic
    def send(
        self,
        *,
        actor: Any = None,
        subject: str | None = None,
        intro: str | None = None,
        signoff: str | None = None,
    ) -> Quotation:
        """DRAFT → SENT via the in-app SMTP path.

        Delegates the downstream state writes (status flip, enquiry
        transition, EnquiryEvent, Zoho push queueing) to the shared
        `record_quote_sent` helper so the manual-mark endpoint produces
        identical state. Fires the `quotation_sent` signal afterwards so
        `comms.signals.quotation_sent_handler` can dispatch the email.

        Optional `subject`/`intro`/`signoff` are operator copy overrides:
        they ride the signal so `quotation_sent_handler` can thread them into
        `build_quotation_context` and the guest email reflects the edited copy.
        """
        # Local import — keeps the service module out of the model's import
        # graph and matches the existing `quotation_sent` signal pattern.
        from reservations.services.quotation_transmission import (
            SEND_PATH_SMTP,
            record_quote_sent,
        )
        from reservations.signals import quotation_sent

        record_quote_sent(self, send_path=SEND_PATH_SMTP, actor=actor)
        quotation_sent.send(
            sender=Quotation,
            quotation=self,
            subject=subject,
            intro=intro,
            signoff=signoff,
        )
        return self

    @transaction.atomic
    def accept(self, line: QuotationLine, *, actor: Any = None) -> Quotation:
        """SENT → ACCEPTED. Marks `line.is_selected=True` and, when the
        quotation is attached to an enquiry, flips that parent enquiry to
        CONVERTED inside the same atomic block — conversion is measured
        per Enquiry (see `django_res_design/10-decisions.md`).
        """
        # Lock + re-read before the guard: a stale instance (double-click,
        # concurrent convert) must not re-accept — or re-point the accepted
        # line — once the row has moved on.
        refresh_locked(self)
        self._assert_from((QuotationStatus.SENT.value,), QuotationStatus.ACCEPTED.value)
        if line.quotation_id != self.pk:
            raise ValueError("Line does not belong to this quotation")
        # Ensure no other line is currently selected (DB-level partial unique
        # still allows zero or one selected line — we set it as the chosen).
        QuotationLine.objects.filter(quotation=self, is_selected=True).exclude(pk=line.pk).update(
            is_selected=False
        )
        line.is_selected = True
        line.save(update_fields=["is_selected", "updated_at"])
        self.status = QuotationStatus.ACCEPTED.value
        self.save(update_fields=["status", "updated_at"])
        # Roll the parent enquiry forward if one is attached and is in an
        # eligible source state. Agent-direct quotations have no enquiry,
        # so this is a no-op for them. Any exception here propagates and
        # rolls the entire accept() atomic block back.
        enquiry = self.enquiry
        if enquiry is not None and enquiry.status in (
            EnquiryStatus.QUOTED.value,
            EnquiryStatus.CONTACTED.value,
        ):
            enquiry.convert(self, actor=actor)
        return self

    @transaction.atomic
    def expire(self) -> Quotation:
        """DRAFT/SENT → EXPIRED. Called by the Celery beat after `expires_at` passes.

        Both live states age out: a DRAFT never sent to the guest is just as
        stale once `expires_at` passes as a SENT one, and the sweeper shouldn't
        have to leave un-sent drafts lingering (the time-based EXPIRED status
        keeps them distinct from an operator's DRAFT → CANCELLED).
        """
        refresh_locked(self)
        self._assert_from(
            (QuotationStatus.DRAFT.value, QuotationStatus.SENT.value),
            QuotationStatus.EXPIRED.value,
        )
        self.status = QuotationStatus.EXPIRED.value
        self.save(update_fields=["status", "updated_at"])
        return self

    @transaction.atomic
    def cancel(self, reason: str = "") -> Quotation:
        """Any non-terminal → CANCELLED."""
        refresh_locked(self)
        self._assert_from(
            (QuotationStatus.DRAFT.value, QuotationStatus.SENT.value),
            QuotationStatus.CANCELLED.value,
        )
        self.status = QuotationStatus.CANCELLED.value
        self.cancel_reason = reason
        self.save(update_fields=["status", "cancel_reason", "updated_at"])
        return self


class QuotationLine(AuditedModel):
    """One option (property + dates) inside a quotation."""

    objects = QuotationLineQuerySet.as_manager()

    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.PROTECT,
        related_name="quotation_lines",
    )
    # Per-line currency (GAP-014, legacy `VillaQuotationDetails.CurrencyId`).
    # Stamped from the engine result for priced lines; manual lines default
    # via the canonical `resolve_property_currency` chain.
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        related_name="+",
    )
    date_from = models.DateField()
    date_to = models.DateField()
    adults = models.PositiveSmallIntegerField()
    children = models.PositiveSmallIntegerField(default=0)
    pricing_snapshot = models.JSONField(default=dict)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    inclusions = models.TextField(blank=True)
    price_override_reason = models.TextField(blank=True)
    is_selected = models.BooleanField(default=False)
    is_manual = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(date_from__lt=models.F("date_to")),
                name="quotationline_date_from_lt_date_to",
            ),
            models.UniqueConstraint(
                fields=["quotation"],
                condition=Q(is_selected=True),
                name="one_selected_line_per_quotation",
            ),
        ]
        ordering = ["pk"]

    def __str__(self) -> str:
        return f"Line #{self.pk} of {self.quotation_id}"
