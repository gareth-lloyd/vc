from __future__ import annotations

from django.db import models

from core.models.base import AuditedModel
from owners.enums import OwnerOrgStatus


class OwnerOrganisation(AuditedModel):
    """A villa-owning party that may log in to the owner portal.

    This is the multi-tenant identity axis for owners: a login `User` becomes
    an owner by holding an `ACTIVE` `OwnerMembership` of one of these. An org
    may own several villas (one `OwnerOrgProperty` grant each), and a single
    villa may be co-owned by more than one org (one grant per org).

    Net-new to the rebuild — the legacy system had no owner-facing identity —
    so there is no `legacy_id`.
    """

    name = models.CharField(max_length=255)
    tax_number = models.CharField(max_length=64, blank=True)
    billing_address = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=OwnerOrgStatus.choices,
        default=OwnerOrgStatus.ACTIVE,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
