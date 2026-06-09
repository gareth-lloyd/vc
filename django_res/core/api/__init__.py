"""Shared API helpers (exception handler, permission classes, response shapes)."""

from __future__ import annotations

from core.api.exception_handler import canonical_exception_handler
from core.api.pagination import ConfigurablePageSizePagination
from core.api.permissions import (
    AllowAnyReadStaffWrite,
    IsAccountsWriter,
    IsReservationsWriter,
    IsStaff,
    IsStaffRoleAdmin,
)
from core.api.responses import not_implemented_response

__all__ = [
    "AllowAnyReadStaffWrite",
    "ConfigurablePageSizePagination",
    "IsAccountsWriter",
    "IsReservationsWriter",
    "IsStaff",
    "IsStaffRoleAdmin",
    "canonical_exception_handler",
    "not_implemented_response",
]
