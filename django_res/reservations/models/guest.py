"""Guest — the unified guest/contact entity used by Enquiry/Quotation/Booking."""

from __future__ import annotations

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from core.fields import CIEmailField
from core.models.base import AuditedModel
from reservations.enums import ContactMethod, GuestStatus


class Guest(AuditedModel):
    """End-customer record (reused across enquiry → quotation → booking)."""

    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)
    title = models.CharField(max_length=16, blank=True)
    email = CIEmailField(db_index=True)
    phone = models.CharField(max_length=32, blank=True)

    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    town = models.CharField(max_length=128, blank=True)
    post_code = models.CharField(max_length=32, blank=True)
    country = models.ForeignKey(
        "properties.Country",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    contact_method = models.CharField(
        max_length=8,
        choices=ContactMethod.choices,
        null=True,
        blank=True,
    )
    marketing_consent = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    status = models.CharField(
        max_length=16,
        choices=GuestStatus.choices,
        default=GuestStatus.ACTIVE,
    )
    anonymized_at = models.DateTimeField(null=True, blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guest",
    )

    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "last_name", "first_name"]),
            models.Index(fields=["email"]),
        ]
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        if self.status == GuestStatus.ANONYMIZED:
            return f"[redacted guest #{self.pk}]"
        return f"{self.first_name} {self.last_name}".strip()

    @transaction.atomic
    def anonymize(self) -> None:
        """Overwrite PII with sentinels; preserves the row for FK integrity."""
        self.first_name = "[REDACTED]"
        self.last_name = "[REDACTED]"
        self.email = f"redacted-{self.pk}@anonymized.local"
        self.phone = ""
        self.address_line_1 = ""
        self.address_line_2 = ""
        self.town = ""
        self.post_code = ""
        self.notes = ""
        self.marketing_consent = False
        self.status = GuestStatus.ANONYMIZED
        self.anonymized_at = timezone.now()
        self.save(
            update_fields=[
                "first_name",
                "last_name",
                "email",
                "phone",
                "address_line_1",
                "address_line_2",
                "town",
                "post_code",
                "notes",
                "marketing_consent",
                "status",
                "anonymized_at",
                "updated_at",
            ]
        )

    @transaction.atomic
    def merge(self, target: Guest) -> None:
        """Rewrite FKs pointing at `self` to point at `target`, then hard-delete self.

        Destructive: no merged_into back-reference. AuditLog is the only trail.
        """
        if target.pk == self.pk:
            raise ValueError("Cannot merge a guest into itself")
        for rel in self._meta.related_objects:
            related_model = rel.related_model
            if related_model is None or isinstance(related_model, str):
                continue
            if rel.many_to_many:
                continue
            field_name = rel.field.name
            related_model._default_manager.filter(**{field_name: self}).update(
                **{field_name: target}
            )
        self.delete()
