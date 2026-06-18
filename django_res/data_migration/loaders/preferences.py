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
        quotation = (
            Quotation.objects.filter(legacy_id=str(row["QuotationMasterId"])).first()
            if row.get("QuotationMasterId")
            else None
        )
        # The unique constraint covers (person, preference_type, quotation) as of
        # GAP-045 Unit 3d-A; this guest-keyed dedup stays correct because guest →
        # person is 1:1, and `guest`/`person` are repointed together in 3d-B.
        # Duplicates (same triple) are collapsed to the first occurrence so the
        # loader stays idempotent on re-runs.
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
        # GAP-045 Unit 3c-1b: mirror the unified Person FK alongside the Guest.
        # `guest` is non-None here (returned early above otherwise). This lands
        # in `defaults` (create-only) via BaseLoader._process_row, so re-runs of
        # this idempotent loader rely on the `link_person_fks` delta linker to
        # fill any rows written before this change.
        return {
            "guest": guest,
            "person": person_for_guest(guest),
            "preference_type": pref_type,
            "quotation": quotation,
        }
