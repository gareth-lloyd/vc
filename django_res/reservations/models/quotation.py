"""Quotation and QuotationLine."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from core.exceptions import InvalidTransition
from core.models.base import AuditedModel
from core.refs import generate_reference
from reservations.enums import QuotationStatus


class Quotation(AuditedModel):
    """Operator-issued quote — DRAFT → SENT → ACCEPTED / EXPIRED / CANCELLED."""

    reference = models.CharField(max_length=32, unique=True)
    enquiry = models.ForeignKey(
        "reservations.Enquiry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
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
    currency = models.ForeignKey(
        "pricing.Currency",
        on_delete=models.PROTECT,
        related_name="+",
    )
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
            self.reference = generate_reference("Q", model=type(self))
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------
    def _assert_from(self, allowed_from: tuple[str, ...], to: str) -> None:
        if self.status not in allowed_from:
            raise InvalidTransition(self.status, to, allowed=list(allowed_from))

    @transaction.atomic
    def send(self) -> Quotation:
        """DRAFT → SENT. Sets `expires_at` if currently null."""
        self._assert_from((QuotationStatus.DRAFT.value,), QuotationStatus.SENT.value)
        self.status = QuotationStatus.SENT.value
        update_fields = ["status", "updated_at"]
        if self.expires_at is None:
            self.expires_at = timezone.now() + timedelta(days=7)
            update_fields.append("expires_at")
        self.save(update_fields=update_fields)
        return self

    @transaction.atomic
    def accept(self, line: QuotationLine) -> Quotation:
        """SENT → ACCEPTED. Marks `line.is_selected=True`."""
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
        return self

    @transaction.atomic
    def expire(self) -> Quotation:
        """SENT → EXPIRED. Called by the Celery beat after `expires_at` passes."""
        self._assert_from((QuotationStatus.SENT.value,), QuotationStatus.EXPIRED.value)
        self.status = QuotationStatus.EXPIRED.value
        self.save(update_fields=["status", "updated_at"])
        return self

    @transaction.atomic
    def cancel(self, reason: str = "") -> Quotation:
        """Any non-terminal → CANCELLED."""
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
    date_from = models.DateField()
    date_to = models.DateField()
    adults = models.PositiveSmallIntegerField()
    children = models.PositiveSmallIntegerField(default=0)
    pricing_snapshot = models.JSONField(default=dict)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
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
