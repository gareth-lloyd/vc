from __future__ import annotations

from django.db import models
from django.db.models import Q

from accounts.enums import ContactRole
from core.models.base import AuditedModel


class PropertyContactAssignment(AuditedModel):
    """Through model linking a `Property` to an `accounts.Contact` in a role.

    Lifecycle: an open-ended assignment has `end_date IS NULL`; ending the
    relationship sets `end_date`. Rows are never hidden.
    """

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="contact_assignments",
    )
    contact = models.ForeignKey(
        "accounts.Contact",
        on_delete=models.PROTECT,
        related_name="property_assignments",
    )
    role = models.CharField(
        max_length=24,
        choices=ContactRole.choices,
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["property", "contact", "role"],
                condition=Q(end_date__isnull=True),
                name="unique_active_role_assignment",
            ),
            models.UniqueConstraint(
                fields=["property", "role"],
                condition=Q(is_primary=True, end_date__isnull=True),
                name="one_primary_per_role",
            ),
        ]
        ordering = ["property_id", "role"]

    def __str__(self) -> str:
        return f"{self.contact_id} as {self.role} on property #{self.property_id}"
