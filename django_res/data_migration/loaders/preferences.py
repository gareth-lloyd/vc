"""GuestPreferenceType + GuestPreference loaders.

VillaClientPrefMaster (11 rows on ResProd) → GuestPreferenceType (declarative
rename).
ClientPreferenceDetails (836 rows on ResProd) → GuestPreference, joining on the
unified `Person` (GAP-045 D5-3, resolved from the legacy ClientDetailsId with
the quotation fallback in `GuestPreferenceLoader`'s docstring), preference_type,
and optional quotation by legacy_id.
"""

from __future__ import annotations

from typing import Any

import structlog

from accounts.models import Person
from data_migration.base import BaseLoader, LoadReport
from data_migration.declarative import DeclarativeLoader
from data_migration.loaders.sentinels import CLIENT_LEGACY_PREFIX, unknown_client
from reservations.models.preferences import GuestPreference, GuestPreferenceType
from reservations.models.quotation import Quotation

logger = structlog.get_logger(__name__)


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
    """ClientPreferenceDetails -> reservations.GuestPreference.

    GAP-108 U8d — the customer resolution order is client → the row's own
    quotation → sentinel, the chain `QuotationLoader` already uses. From
    ~Nov-2025 ResProd stopped naming VillaClientDetails rows, so an
    unresolvable `ClientDetailsId` is common (569 of 836 rows) and most of them
    have a real, named customer one hop away on the quotation the preference
    was recorded against: 474 reach a named person, leaving 95 legacy rows (30
    loaded, after the dedup below) genuinely anonymous. The hop is bounded by
    `_may_borrow_quotation_person` so it can never merge two real people.

    Registry order is load-bearing: `quotation` runs before `guest_preference`,
    so `Quotation.person` is already resolved when this reads it.
    """

    name = "guest_preference"
    target_model = GuestPreference
    # `ClientRowExists` / `QuotationClientId` exist only to bound the U8d
    # fallback (see `_may_borrow_quotation_person`) — neither is written.
    legacy_query = (
        "SELECT p.Id, p.ClientDetailsId, p.ClientPrefMasterId, p.QuotationMasterId, "
        "CASE WHEN c.Id IS NULL THEN 0 ELSE 1 END AS ClientRowExists, "
        "q.ClientDetailsId AS QuotationClientId "
        "FROM ClientPreferenceDetails p "
        "LEFT JOIN VillaClientDetails c ON c.Id = p.ClientDetailsId "
        "LEFT JOIN VillaQuotationMaster q ON q.Id = p.QuotationMasterId"
    )

    # BUG-030 §30: most legacy `QuotationMasterId`s point at no quotation
    # (126/167 in the reference dump). Those rows still load, flattened to
    # quotation=None; the run logs how many lost their quotation context.
    _unresolved_quotations = 0
    # GAP-108 U8d: how often the customer came from the quotation rather than
    # the row's own client, and how often the guard below refused that hop.
    # Counted for the same reason as the above — so a dry run on a NEWER dump
    # can see the fallback's reach change instead of inferring it from a moved
    # reconcile gap. 13-Aug-2026: count=514, refused=0. The 514 is 474 rows
    # reaching a named person plus 40 whose quotation is ITSELF on the sentinel
    # (a borrow that changes nothing, hence counted but invisible downstream).
    _borrowed_from_quotation = 0
    _refused_borrow = 0

    def _load_rows(self, rows: list[dict[str, Any]], report: LoadReport) -> None:
        self._unresolved_quotations = 0
        self._borrowed_from_quotation = 0
        self._refused_borrow = 0
        super()._load_rows(rows, report)
        logger.info(
            "data_migration.preference_quotation_unresolved",
            count=self._unresolved_quotations,
        )
        logger.info(
            "data_migration.preference_customer_borrowed_from_quotation",
            count=self._borrowed_from_quotation,
            refused=self._refused_borrow,
        )

    @staticmethod
    def _may_borrow_quotation_person(row: dict[str, Any]) -> bool:
        """May an unresolvable-client preference take its quotation's customer?

        Only when that cannot put one person's preferences (dietary, access,
        VIP notes — PII) on another person's profile. Two safe shapes:

        * the preference's `ClientDetailsId` matches no `VillaClientDetails`
          row at all, so it names nobody to be wrong about. This is the bulk of
          the real cases — legacy's hard-coded placeholder id 1 plus a handful
          of other junk ids ({1, 5, 17, 167, 397} on the 13-Aug-2026 dump,
          none of them a real client row);
        * the quotation names the SAME client id, so its `person` is the same
          human, reached through the enquiry hop U8b gave `QuotationLoader`.

        Refused otherwise: a preference on a client row that EXISTS but did not
        load (the 184 rows named nowhere, `reconcile_legacy` Person (client))
        belongs to a real, distinct person, and its quotation naming somebody
        else is not licence to merge them. Such a row keeps the sentinel. Zero
        rows on the 13-Aug-2026 dump — this bounds a FUTURE dump, since the
        cutover reloads from a newer one.
        """
        if not row.get("ClientRowExists"):
            return True
        return str(row.get("QuotationClientId") or "") == str(row.get("ClientDetailsId") or "")

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        pref_type = GuestPreferenceType.objects.filter(
            legacy_id=str(row.get("ClientPrefMasterId") or ""),
        ).first()
        if pref_type is None:
            return None
        # Resolved BEFORE the customer: U8d's fallback reads its `person`.
        quotation = (
            Quotation.objects.filter(legacy_id=str(row["QuotationMasterId"]))
            .select_related("person")
            .first()
            if row.get("QuotationMasterId")
            else None
        )
        if row.get("QuotationMasterId") and quotation is None:
            self._unresolved_quotations += 1
        # A row naming neither a client nor a loaded quotation references no
        # customer at all; it is a preference type attached to nobody, so it is
        # dropped rather than piled onto the sentinel (GAP-045 D5-3's original
        # `guest is None` skip). 0 such rows on the 13-Aug-2026 dump.
        if not row.get("ClientDetailsId") and quotation is None:
            return None
        # GAP-108 U8d: client → this row's own quotation → sentinel. The client
        # lookup is direct rather than `person_for_client`, which mints the
        # sentinel eagerly — here it must stay the last resort, exactly as in
        # `QuotationLoader.transform`.
        person = (
            Person.objects.filter(
                legacy_id=f"{CLIENT_LEGACY_PREFIX}{row['ClientDetailsId']}"
            ).first()
            if row.get("ClientDetailsId")
            else None
        )
        if person is None and quotation is not None:
            if self._may_borrow_quotation_person(row):
                person = quotation.person
                self._borrowed_from_quotation += 1
            else:
                self._refused_borrow += 1
        if person is None:
            person = unknown_client()
        # GAP-045 D5-3: the dedup is keyed on the unified `person` to match the
        # `unique_person_preference` constraint (person, preference_type,
        # quotation). Duplicates (same triple) collapse to the first occurrence
        # so the loader stays idempotent. U8d's fallback moves 474 rows OFF the
        # shared sentinel and so changes this key, but not the counts: a
        # surviving collapse either has quotation=NULL (no fallback to apply) or
        # shares its quotation, hence its borrowed person, with its twin. No
        # moved row lands on a triple a resolvable-client row already owns
        # (replayed over the 13-Aug-2026 dump: 635 loaded / 201 skipped either
        # way, so the `expected_gap=201` pinned in U8c is unmoved).
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
