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
from reservations.services.person_sync import person_for_guest


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
        person = person_for_guest(guest)
        quotation = (
            Quotation.objects.filter(legacy_id=str(row["QuotationMasterId"])).first()
            if row.get("QuotationMasterId")
            else None
        )
        # GAP-045 Unit 3d-B: the dedup is keyed on `person` to match the
        # `unique_person_preference` constraint (person, preference_type,
        # quotation) — `person` is now the sole customer FK written, so a
        # guest-keyed dedup would stop matching prior rows (born guest-NULL) on
        # re-run and trip the constraint. guest → person is 1:1 (mirror key
        # `guest-{pk}`), so this is exactly equivalent. Duplicates (same triple)
        # collapse to the first occurrence so the loader stays idempotent.
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
