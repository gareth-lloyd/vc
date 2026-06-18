from __future__ import annotations

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from accounts.enums import (
    EmailLabel,
    PersonPreferredMethod,
    PersonStatus,
    PhoneLabel,
)
from core.audit import record_merge, scrub_pii
from core.fields import CIEmailField
from core.models.base import AuditedModel, TimestampedModel

# GAP-045: the namespaced ``legacy_id`` prefix stamped on Persons back-filled
# from ``reservations.Guest`` (migration reservations/0033). A migration-only
# sentinel — never an application lookup key. Used to filter Guest-derived rows
# out of the owner/agent ``/contacts`` directory until Unit 3c reworks it into a
# proper filtered view. Mirror of the literal in that migration (frozen there).
GUEST_LEGACY_PREFIX = "guest-"


class Person(AuditedModel):
    """Villa owner, property manager, or external agent.

    Distinct from `User` because most people never log in. If they do,
    we link via the optional `user` OneToOne.
    """

    title = models.CharField(max_length=16, blank=True)
    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)
    company = models.CharField(max_length=128, blank=True)
    website_url = models.URLField(blank=True)
    preferred_method = models.CharField(
        max_length=8,
        choices=PersonPreferredMethod.choices,
        default=PersonPreferredMethod.EMAIL,
    )
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
    marketing_consent = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=PersonStatus.choices,
        default=PersonStatus.ACTIVE,
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

    # Audit-tracked columns carrying cleartext PII. Erasure flows scrub these
    # from the AuditLog trail (BUG-012); non-PII tracked columns (status) stay.
    _AUDIT_PII_FIELDS = (
        "title",
        "first_name",
        "last_name",
        "company",
        "address_line_1",
        "address_line_2",
        "town",
        "post_code",
        "notes",
    )

    class Meta:
        indexes = [
            models.Index(fields=["status", "last_name", "first_name"]),
        ]
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        if self.status == PersonStatus.ANONYMIZED:
            return f"[redacted person #{self.pk}]"
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_name(self) -> str | None:
        """Full name for staff lists, or ``None`` when both name parts blank."""
        return f"{self.first_name} {self.last_name}".strip() or None

    def primary_email(self) -> str | None:
        """Primary email address, read from the prefetch cache.

        Iterates ``self.emails.all()`` (so it stays inside a
        ``prefetch_related("emails")`` budget rather than firing a fresh
        ``.filter()`` per row). Returns the ``is_primary`` address, else the
        oldest by pk — matching ``comms.recipients._primary_contact_email``.
        Guest mirrors always carry exactly one PRIMARY (GAP-045 Unit 3c-1a),
        so the oldest-by-pk fallback only matters for non-mirror Persons.

        Fails closed for an ANONYMIZED Person: ``Person.anonymize`` rewrites
        each PersonEmail to a syntactically-valid ``redacted-…@anonymized.local``
        sentinel and keeps the row, so without this guard a person-first read
        (staff list or comms send) would surface — and mail — that sentinel.
        Returning ``None`` here is the single chokepoint that protects both.
        """
        if self.status == PersonStatus.ANONYMIZED:
            return None
        emails = list(self.emails.all())
        if not emails:
            return None
        for email in emails:
            if email.is_primary:
                return email.email
        return min(emails, key=lambda e: e.pk).email

    def primary_phone(self) -> str | None:
        """Primary phone number from the prefetch cache (see ``primary_email``).

        Fails closed for an ANONYMIZED Person, mirroring ``primary_email``.
        """
        if self.status == PersonStatus.ANONYMIZED:
            return None
        phones = list(self.phones.all())
        if not phones:
            return None
        for phone in phones:
            if phone.is_primary:
                return phone.number or None
        return min(phones, key=lambda p: p.pk).number or None

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
        self.town = ""
        self.post_code = ""
        self.status = PersonStatus.ANONYMIZED
        self.anonymized_at = timezone.now()
        self.save(
            update_fields=[
                "first_name",
                "last_name",
                "company",
                "notes",
                "address_line_1",
                "address_line_2",
                "town",
                "post_code",
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
        # Scrub *after* the save so the freshly written [old, sentinel] row is
        # caught alongside the historical trail (BUG-012).
        scrub_pii(self, self._AUDIT_PII_FIELDS)

    @transaction.atomic
    def merge(self, target: Person) -> None:
        """Rewrite FKs pointing at `self` to point at `target`, then hard-delete self.

        Destructive: there is no merged_into back-reference. The AuditLog is
        the only trail.
        """
        if target.pk == self.pk:
            raise ValueError("Cannot merge a person into itself")
        # Apps that hold FKs to Person are properties.PropertyContactAssignment,
        # reservations.Enquiry/Quotation/Booking (agent FKs),
        # properties.PropertyFinance.contact. Their migrations create the
        # reverse relations; we rewrite via _meta.related_objects so the merge
        # works without hard-coding which apps exist yet.
        # The .update() rewrites bypass the audit signals, so record a summary
        # of what moved (per-relation counts) onto the deletion row (FG-016).
        rewrites: dict[str, int] = {}
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


class PersonEmail(TimestampedModel):
    contact = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="emails")
    email = CIEmailField()
    label = models.CharField(max_length=16, choices=EmailLabel.choices, default=EmailLabel.PRIMARY)
    is_primary = models.BooleanField(default=False)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

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


class PersonPhone(TimestampedModel):
    contact = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="phones")
    number = models.CharField(max_length=32)
    label = models.CharField(max_length=16, choices=PhoneLabel.choices, default=PhoneLabel.MOBILE)
    is_primary = models.BooleanField(default=False)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

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
