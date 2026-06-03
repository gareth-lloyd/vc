from __future__ import annotations

from django.db import models
from django.db.models import Q

from core.models.base import AuditedModel


class OwnerOrgProperty(AuditedModel):
    """Grant linking an `OwnerOrganisation` to a `Property` it may view.

    This is both the org↔property membership edge *and* the carrier of the
    per-property visibility flags. Defaults are **opt-in / hidden**: a fresh
    grant shows neither money nor guest contact; VC widens visibility per
    property by flipping `view_full_money` / `view_guest_details` (resolves
    Q-015 at per-org↔property granularity).

    Co-owned villas are modelled as two rows with different `organisation`s.
    Lifecycle is `end_date`: an open grant has `end_date IS NULL`; ending the
    relationship sets it (no soft-delete column).

    Distinct from `properties.PropertyContactAssignment(role=owner)`, which
    answers "who is the ops/payout *contact*". This answers "which login org
    may *view* this property, and with what visibility". The two are
    orthogonal and must not be DRYed together.

    The FK lives here (not as an M2M field on `Property`) deliberately: it
    keeps the dependency edge pointing `owners → properties`, never the
    reverse. Traverse from this model — same one-directional pattern as
    `PropertyContactAssignment`.
    """

    organisation = models.ForeignKey(
        "owners.OwnerOrganisation",
        on_delete=models.CASCADE,
        related_name="property_grants",
    )
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        related_name="owner_grants",
    )
    view_full_money = models.BooleanField(default=False)
    view_guest_details = models.BooleanField(default=False)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "property"],
                condition=Q(end_date__isnull=True),
                name="unique_active_org_property_grant",
            ),
        ]
        ordering = ["organisation_id", "property_id"]

    def __str__(self) -> str:
        return f"org #{self.organisation_id} → property #{self.property_id}"
