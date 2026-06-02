from __future__ import annotations

from django.db import models


class StaffRole(models.TextChoices):
    """Internal staff authorisation role.

    Lives in `core` (not `accounts`) because it is an auth/permission
    primitive consumed by the cross-cutting permission layer
    (`core.api.permissions`); keeping it here lets `core` stay free of any
    upward dependency into a domain app.
    """

    ADMIN = "admin", "Admin"
    RESERVATIONS = "reservations", "Reservations"
    ACCOUNTS = "accounts", "Accounts"
    VIEWER = "viewer", "Viewer"
