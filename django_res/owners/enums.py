from __future__ import annotations

from django.db import models


class OwnerOrgStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"


class OwnerRole(models.TextChoices):
    """Role of a user within an owner organisation.

    The full set is stored for forward-compatibility, but v1 only exercises
    `ADMIN`; no endpoint branches on role yet. Finer-grained RBAC is a
    deferred surface (see the Owner Portal MVP plan).
    """

    ADMIN = "admin", "Admin"
    PROPERTY_MANAGER = "property_manager", "Property manager"
    FINANCE = "finance", "Finance"
    EDITOR = "editor", "Editor"
    VIEW_ONLY = "view_only", "View only"


class OwnerMembershipStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    REMOVED = "removed", "Removed"
