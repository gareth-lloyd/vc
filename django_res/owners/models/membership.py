from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models.base import AuditedModel
from owners.enums import OwnerMembershipStatus, OwnerRole


class OwnerMembership(AuditedModel):
    """Links a login `User` to an `OwnerOrganisation` in a role.

    A user is an *owner* iff they hold an `ACTIVE` membership of at least one
    org — there is deliberately no `OWNER` value on `core.StaffRole` and no
    flag on `User`, so staff authz stays owner-blind and one person can be
    both staff and an owner.

    v1 visibility rule: a member sees **all** properties granted to their org.
    Per-member property subsetting is a deferred surface; when it lands it will
    be a nullable through-model whose absence still means ALL. No endpoint
    branches on `role` in v1 — the full `OwnerRole` set is stored only for
    forward-compatibility.
    """

    organisation = models.ForeignKey(
        "owners.OwnerOrganisation",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owner_memberships",
    )
    role = models.CharField(
        max_length=24,
        choices=OwnerRole.choices,
        default=OwnerRole.ADMIN,
    )
    status = models.CharField(
        max_length=16,
        choices=OwnerMembershipStatus.choices,
        default=OwnerMembershipStatus.PENDING,
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    invited_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "user"],
                name="unique_membership_per_org_user",
            ),
        ]
        indexes = [
            # Powers IsOwner / scoping: "active memberships for this user".
            models.Index(fields=["user", "status"], name="ownermembership_user_status"),
        ]
        ordering = ["organisation_id", "user_id"]

    def __str__(self) -> str:
        return f"user #{self.user_id} in org #{self.organisation_id} ({self.role})"
