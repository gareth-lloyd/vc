"""GuestPreferenceType + GuestPreference loaders.

VillaClientPrefMaster (13 rows) → GuestPreferenceType (declarative rename).
ClientPreferenceDetails (167 rows) → GuestPreference, joining on guest,
preference_type, and optional quotation by legacy_id.
"""

from __future__ import annotations

from typing import Any

from data_migration.base import BaseLoader
from data_migration.declarative import DeclarativeLoader
from reservations.models.guest import Guest
from reservations.models.preferences import GuestPreference, GuestPreferenceType
from reservations.models.quotation import Quotation


class GuestPreferenceTypeLoader(DeclarativeLoader):
    name = "guest_preference_type"
    legacy_table = "VillaClientPrefMaster"
    target_model = GuestPreferenceType
    field_map = {
        "Name": "name",
        "IsActive": "is_active",
    }

    def transform_extra(self, row: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any] | None:
        name = (kwargs.get("name") or "").strip()
        if not name:
            return None
        kwargs["name"] = name[:128]
        kwargs["is_active"] = bool(kwargs.get("is_active"))
        return kwargs


class GuestPreferenceLoader(BaseLoader):
    name = "guest_preference"
    target_model = GuestPreference
    legacy_query = (
        "SELECT Id, ClientDetailsId, ClientPrefMasterId, QuotationMasterId "
        "FROM ClientPreferenceDetails"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        guest = Guest.objects.filter(legacy_id=str(row.get("ClientDetailsId") or "")).first()
        pref_type = GuestPreferenceType.objects.filter(
            legacy_id=str(row.get("ClientPrefMasterId") or ""),
        ).first()
        if guest is None or pref_type is None:
            return None
        quotation = (
            Quotation.objects.filter(legacy_id=str(row["QuotationMasterId"])).first()
            if row.get("QuotationMasterId")
            else None
        )
        # The unique constraint covers (guest, preference_type, quotation).
        # Duplicates (same triple) are collapsed to the first occurrence so
        # the loader stays idempotent on re-runs.
        existing = (
            GuestPreference.objects.filter(
                guest=guest,
                preference_type=pref_type,
                quotation=quotation,
            )
            .exclude(legacy_id=str(row["Id"]))
            .first()
        )
        if existing is not None:
            return None
        return {
            "guest": guest,
            "preference_type": pref_type,
            "quotation": quotation,
        }
