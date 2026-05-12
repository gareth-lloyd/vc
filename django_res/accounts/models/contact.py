from __future__ import annotations

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from accounts.enums import (
    ContactPreferredMethod,
    ContactStatus,
    EmailLabel,
    PhoneLabel,
)
from core.fields import CIEmailField
from core.models.base import AuditedModel, TimestampedModel


class Contact(AuditedModel):
    """Villa owner, property manager, or external agent.

    Distinct from `User` because most contacts never log in. If they do,
    we link via the optional `user` OneToOne.
    """

    title = models.CharField(max_length=16, blank=True)
    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)
    company = models.CharField(max_length=128, blank=True)
    website_url = models.URLField(blank=True)
    preferred_method = models.CharField(
        max_length=8,
        choices=ContactPreferredMethod.choices,
        default=ContactPreferredMethod.EMAIL,
    )
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=ContactStatus.choices,
        default=ContactStatus.ACTIVE,
    )
    anonymized_at = models.DateTimeField(null=True, blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contact",
    )
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "last_name", "first_name"]),
        ]
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        if self.status == ContactStatus.ANONYMIZED:
            return f"[redacted contact #{self.pk}]"
        return f"{self.first_name} {self.last_name}".strip()

    @transaction.atomic
    def anonymize(self) -> None:
        """Overwrite PII with sentinels and flip status.

        Row is preserved for FK integrity on historical bookings.
        Email/phone children are anonymized in lockstep.
        """
        self.first_name = "[REDACTED]"
        self.last_name = "[REDACTED]"
        self.company = ""
        self.notes = ""
        self.address_line_1 = ""
        self.address_line_2 = ""
        self.status = ContactStatus.ANONYMIZED
        self.anonymized_at = timezone.now()
        self.save(
            update_fields=[
                "first_name",
                "last_name",
                "company",
                "notes",
                "address_line_1",
                "address_line_2",
                "status",
                "anonymized_at",
                "updated_at",
            ]
        )
        for email in self.emails.all():
            email.email = f"redacted-{email.pk}@anonymized.local"
            email.save(update_fields=["email", "updated_at"])
        for phone in self.phones.all():
            phone.number = ""
            phone.save(update_fields=["number", "updated_at"])

    @transaction.atomic
    def merge(self, target: Contact) -> None:
        """Rewrite FKs pointing at `self` to point at `target`, then hard-delete self.

        Destructive: there is no merged_into back-reference. The AuditLog is
        the only trail.
        """
        if target.pk == self.pk:
            raise ValueError("Cannot merge a contact into itself")
        # Apps that hold FKs to Contact are properties.PropertyContactAssignment,
        # reservations.Enquiry/Quotation/Booking (agent FKs),
        # properties.PropertyFinance.contact. Their migrations create the
        # reverse relations; we rewrite via _meta.related_objects so the merge
        # works without hard-coding which apps exist yet.
        for rel in self._meta.related_objects:
            related_model = rel.related_model
            if related_model is None or isinstance(related_model, str):
                continue
            # Skip M2M reverse relations: the through model shows up separately
            # as its own FK relation and is rewritten there. .update() on an
            # M2M field raises FieldError because it isn't a column.
            if rel.many_to_many:
                continue
            field_name = rel.field.name
            related_model._default_manager.filter(**{field_name: self}).update(
                **{field_name: target}
            )
        self.delete()


class ContactEmail(TimestampedModel):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="emails")
    email = CIEmailField()
    label = models.CharField(max_length=16, choices=EmailLabel.choices, default=EmailLabel.PRIMARY)
    is_primary = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["contact", "email"],
                name="unique_contact_email",
            ),
            models.UniqueConstraint(
                fields=["contact"],
                condition=Q(is_primary=True),
                name="one_primary_email_per_contact",
            ),
        ]


class ContactPhone(TimestampedModel):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="phones")
    number = models.CharField(max_length=32)
    label = models.CharField(max_length=16, choices=PhoneLabel.choices, default=PhoneLabel.MOBILE)
    is_primary = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["contact", "number"],
                name="unique_contact_phone",
            ),
            models.UniqueConstraint(
                fields=["contact"],
                condition=Q(is_primary=True),
                name="one_primary_phone_per_contact",
            ),
        ]
