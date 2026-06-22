"""GuestPreferenceType + GuestPreference loaders.

VillaClientPrefMaster (13 rows) → GuestPreferenceType (declarative rename).
ClientPreferenceDetails (167 rows) → GuestPreference, joining on the unified
`Person` (resolved from the legacy ClientDetailsId via `person_for_client`,
GAP-045 D5-3), preference_type, and optional quotation by legacy_id.
"""

from __future__ import annotations

from typing import Any

from data_migration.base import BaseLoader
from data_migration.declarative import DeclarativeLoader
from data_migration.loaders._util import person_for_client
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
        person = person_for_client(row.get("ClientDetailsId"))
        pref_type = GuestPreferenceType.objects.filter(
            legacy_id=str(row.get("ClientPrefMasterId") or ""),
        ).first()
        if person is None or pref_type is None:
            return None
        quotation = (
            Quotation.objects.filter(legacy_id=str(row["QuotationMasterId"])).first()
            if row.get("QuotationMasterId")
            else None
        )
        # GAP-045 D5-3: the customer is resolved straight to its unified
        # `Person` (keyed `client-{ClientDetailsId}`) via `person_for_client`,
        # and the dedup is keyed on `person` to match the
        # `unique_person_preference` constraint (person, preference_type,
        # quotation). Duplicates (same triple) collapse to the first occurrence
        # so the loader stays idempotent.
        existing = (
            GuestPreference.objects.filter(
                person=person,
                preference_type=pref_type,
                quotation=quotation,
            )
            .exclude(legacy_id=str(row["Id"]))
            .first()
        )
        if existing is not None:
            return None
        return {
            "person": person,
            "preference_type": pref_type,
            "quotation": quotation,
        }
