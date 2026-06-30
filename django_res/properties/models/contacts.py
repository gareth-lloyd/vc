from __future__ import annotations

from django.db import models
from django.db.models import Q

from accounts.enums import ContactRole
from core.models.base import AuditedModel


class PropertyContactAssignment(AuditedModel):
    """Through model linking a `Property` to an assignee in a role.

    The assignee is exactly one of a `accounts.Person` (`contact`) or an
    `accounts.Organisation` (`organisation`) — the `management_company` role
    points at an Organisation, every other role at a Person. The XOR is enforced
    by `assignment_contact_xor_organisation`.

    Lifecycle: an open-ended assignment has `end_date IS NULL`; ending the
    relationship sets `end_date`. Rows are never hidden.
    """

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="contact_assignments",
    )
    contact = models.ForeignKey(
        "accounts.Person",
        on_delete=models.PROTECT,
        related_name="property_assignments",
        null=True,
        blank=True,
    )
    organisation = models.ForeignKey(
        "accounts.Organisation",
        on_delete=models.PROTECT,
        related_name="property_assignments",
        null=True,
        blank=True,
    )
    role = models.CharField(
        max_length=24,
        choices=ContactRole.choices,
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    legacy_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        constraints = [
            # A Person-assignee active-role uniqueness. NULL `contact` rows (org
            # assignees) are treated as distinct by Postgres, so this never
            # collides on the org path — the org constraint below covers it.
            models.UniqueConstraint(
                fields=["property", "contact", "role"],
                condition=Q(end_date__isnull=True),
                name="unique_active_role_assignment",
            ),
            models.UniqueConstraint(
                fields=["property", "organisation", "role"],
                condition=Q(end_date__isnull=True),
                name="unique_active_role_org_assignment",
            ),
            models.UniqueConstraint(
                fields=["property", "role"],
                condition=Q(is_primary=True, end_date__isnull=True),
                name="one_primary_per_role",
            ),
            models.CheckConstraint(
                condition=(
                    Q(contact__isnull=False, organisation__isnull=True)
                    | Q(contact__isnull=True, organisation__isnull=False)
                ),
                name="assignment_contact_xor_organisation",
            ),
            # An Organisation only ever stands in for the management_company
            # role; every other role is a Person. Enforced at the DB so a loader
            # or direct ORM write can't persist e.g. an org as OWNER (the
            # serializer mirrors this for a 400 instead of a 500). Person rows
            # (organisation IS NULL) are unconstrained — a Person may hold any
            # role, including management_company.
            models.CheckConstraint(
                condition=(Q(organisation__isnull=True) | Q(role=ContactRole.MANAGEMENT_COMPANY)),
                name="org_assignee_only_management_company",
            ),
        ]
        ordering = ["property_id", "role"]

    def __str__(self) -> str:
        assignee = (
            f"contact #{self.contact_id}"
            if self.contact_id is not None
            else f"org #{self.organisation_id}"
        )
        return f"{assignee} as {self.role} on property #{self.property_id}"
