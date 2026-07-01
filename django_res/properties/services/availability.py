"""PropertyAvailabilityService — freshness-touch primitives (GAP-033).

Two write paths for the availability-freshness signals stored on `Property`:

- `touch_owner_updated` — Signal 1 ("last updated by owner"), called from
  `OwnerBlockService` when an owner-sourced (MANUAL) block is created or
  released.
- `confirm` — Signal 3 ("last confirmed by VC staff"), called only from the
  manual confirm endpoint, recording the staff actor.

Each method saves ONLY its own column(s) and deliberately does NOT touch
`updated_at`: a freshness touch is not a property edit, so it must not pollute
"recently updated" sorts. Framework-free (no rest_framework import) so it can be
called from any layer that imports `properties` down the spine.

Naming note: distinct from the unrelated
`reservations.services.availability.AvailabilityService`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from accounts.models import User
    from properties.models import Property


class PropertyAvailabilityService:
    """Write the per-property availability-freshness timestamps."""

    @staticmethod
    def touch_owner_updated(property: Property) -> None:
        """Stamp Signal 1 — owner availability changed just now."""
        property.availability_owner_updated_at = timezone.now()
        property.save(update_fields=["availability_owner_updated_at"])

    @staticmethod
    def confirm(property: Property, *, actor: User) -> None:
        """Stamp Signal 3 — a VC staffer vouched availability is current."""
        property.availability_confirmed_at = timezone.now()
        property.availability_confirmed_by = actor
        property.save(update_fields=["availability_confirmed_at", "availability_confirmed_by"])
