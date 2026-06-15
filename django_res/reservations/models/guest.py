"""Guest — the unified guest/contact entity used by Enquiry/Quotation/Booking."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from core.audit import record_merge, scrub_pii
from core.fields import CIEmailField
from core.models.base import AuditedModel
from reservations.enums import ContactMethod, GuestStatus
from reservations.phone import to_e164


class Guest(AuditedModel):
    """End-customer record (reused across enquiry → quotation → booking)."""

    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)
    title = models.CharField(max_length=16, blank=True)
    email = CIEmailField(db_index=True, null=True, blank=True)
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

    # Audit-tracked columns carrying cleartext PII. Erasure flows scrub these
    # from the AuditLog trail (BUG-012); the non-PII tracked columns
    # (status, contact_method, marketing_consent, anonymized_at) stay readable.
    _AUDIT_PII_FIELDS = (
        "first_name",
        "last_name",
        "email",
        "phone",
        "address_line_1",
        "address_line_2",
        "town",
        "post_code",
        "notes",
    )

    class Meta:
        indexes = [
            models.Index(fields=["status", "last_name", "first_name"]),
            models.Index(fields=["email"]),
        ]
        constraints = [
            # Honest integrity, ACTIVE rows only — ARCHIVED/ANONYMIZED are
            # exempt (a dispositioned channel-less row, or a redacted one,
            # must not fail these). See django_res_design/people-model-cleanup.md.
            #
            # Contactable by at least one channel.
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=GuestStatus.ACTIVE.value)
                    | models.Q(email__isnull=False)
                    | ~models.Q(phone="")
                ),
                name="guest_active_contactable",
            ),
            # A stated preference must be actionable — you can only prefer a
            # channel you've actually provided.
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=GuestStatus.ACTIVE.value)
                    | (
                        (
                            ~models.Q(contact_method=ContactMethod.EMAIL.value)
                            | models.Q(email__isnull=False)
                        )
                        & (
                            ~models.Q(
                                contact_method__in=[
                                    ContactMethod.PHONE.value,
                                    ContactMethod.SMS.value,
                                ]
                            )
                            | ~models.Q(phone="")
                        )
                    )
                ),
                name="guest_active_preference_actionable",
            ),
        ]
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        if self.status == GuestStatus.ANONYMIZED:
            return f"[redacted guest #{self.pk}]"
        return f"{self.first_name} {self.last_name}".strip()

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Normalize contact channels on every write so the CHECKs see the truth.

        - `phone` → E.164 (unanchorable national numbers pass through unchanged,
          see `reservations.phone`).
        - empty-string `email` → NULL. An empty email is the *absence* of an
          email, but `email__isnull=False` would treat "" as present and let an
          uncontactable ACTIVE guest past `guest_active_contactable` on any path
          that bypasses the serializer (admin, ORM, bulk). Collapsing it here
          converges every write path on one rule.
        """
        if self.phone:
            self.phone = to_e164(self.phone)
        if not self.email:
            self.email = None
        super().save(*args, **kwargs)

    @transaction.atomic
    def anonymize(self) -> None:
        """Overwrite PII with sentinels; preserves the row for FK integrity."""
        self.first_name = "[REDACTED]"
        self.last_name = "[REDACTED]"
        self.email = None
        self.phone = ""
        self.contact_method = None
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
                "contact_method",
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
        # Scrub *after* the save so the freshly written [old, sentinel] row is
        # caught alongside the historical trail (BUG-012).
        scrub_pii(self, self._AUDIT_PII_FIELDS)

    @transaction.atomic
    def merge(self, target: Guest) -> None:
        """Rewrite FKs pointing at `self` to point at `target`, then hard-delete self.

        Destructive: no merged_into back-reference. AuditLog is the only trail.
        """
        if target.pk == self.pk:
            raise ValueError("Cannot merge a guest into itself")
        # The .update() rewrites bypass the audit signals, so record a summary
        # of what moved (per-relation counts) onto the deletion row (FG-016).
        rewrites: dict[str, int] = {}
        for rel in self._meta.related_objects:
            related_model = rel.related_model
            if related_model is None or isinstance(related_model, str):
                continue
            if rel.many_to_many:
                continue
            field_name = rel.field.name
            count = related_model._default_manager.filter(**{field_name: self}).update(
                **{field_name: target}
            )
            if count:
                rewrites[f"{related_model._meta.label}.{field_name}"] = count
        dead_pk = self.pk
        target_pk = target.pk
        self.delete()
        # Scrub by the now-dead pk so the deletion row's [old_PII, None] pairs
        # are redacted while __deleted__/actor/timestamps survive (BUG-012).
        self.pk = dead_pk
        # Stamp merge summary onto the deletion row *before* scrubbing so the
        # augmented row is scrubbed too (FG-016).
        record_merge(self, target_pk, rewrites)
        scrub_pii(self, self._AUDIT_PII_FIELDS)
