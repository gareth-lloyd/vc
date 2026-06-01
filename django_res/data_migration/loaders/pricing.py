"""Pricing: VillaSeason -> RatePlan + RateCard; VillaSeasonRate -> RateRule.

Legacy structure:
  VillaSeason (id, name, villa_id, notes, inclusion)
    └── VillaSeasonDates (id, season_id, from_date, to_date)
    └── VillaSeasonRate (id, season_id, villa_id, currency_id, from_date,
                        to_date, party_size, price_type, weekly_price,
                        nightly_price, is_poa, ...)

New structure:
  RatePlan (property, currency, effective_from, effective_to)
    └── RateCard (plan, name, ...)
          └── RateRule (card, date_from, date_to, min_party, max_party,
                       nightly, weekly, is_poa, priority)

Strategy:
- One RatePlan per VillaSeason (currency picked from first VillaSeasonRate).
- effective_from/to from min/max of VillaSeasonDates rows.
- One default RateCard per RatePlan (named after the season).
- One RateRule per VillaSeasonRate. priority=row.Id ensures the EXCLUDE
  constraint never trips on legacy overlaps with different priorities.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from data_migration.base import BaseLoader, LoadReport
from pricing.models.currency import Currency
from pricing.models.rate import RateCard, RatePlan, RateRule
from properties.models.property import Property


def _to_decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _resolve_property_currency(prop: Property) -> Currency | None:
    """Resolve currency via the canonical PropertySettings.effective() chain,
    with a table-wide first-row fallback when neither property nor group
    has one configured.
    """
    try:
        currency = prop.settings.effective("currency")
    except Exception:
        currency = None
    return currency or Currency.objects.first()


class RatePlanLoader(BaseLoader):
    """VillaSeason -> RatePlan + default RateCard.

    Picks currency + dates from related VillaSeasonRate / VillaSeasonDates.
    Creates exactly one RateCard per plan (the framework writes it via
    `_process_row` after the plan upsert lands).
    """

    name = "rate_plan"
    target_model = RatePlan
    legacy_pk_column = "ID"
    legacy_query = (
        "SELECT s.ID, s.Name, s.VillaId, s.Notes, s.Inclusion, "
        "(SELECT TOP 1 r.CurrencyId FROM VillaSeasonRate r "
        " WHERE r.SeasonId = s.ID ORDER BY r.ID) AS CurrencyId, "
        "(SELECT MIN(d.FromDate) FROM VillaSeasonDates d WHERE d.SeasonId = s.ID) AS DateFrom, "
        "(SELECT MAX(d.ToDate) FROM VillaSeasonDates d WHERE d.SeasonId = s.ID) AS DateTo "
        "FROM VillaSeason s WHERE s.DeletedAt IS NULL"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        prop = Property.objects.filter(legacy_id=str(row.get("VillaId") or "")).first()
        if prop is None:
            return None
        currency = Currency.objects.filter(legacy_id=str(row.get("CurrencyId") or "")).first()
        if currency is None:
            # Prefer the property/group's own configured currency; only fall
            # back to the table-wide first row when neither is set.
            currency = _resolve_property_currency(prop)
            if currency is None:
                return None
        effective_from = row.get("DateFrom") or date(2020, 1, 1)
        if isinstance(effective_from, str):
            effective_from = date.fromisoformat(effective_from[:10])
        elif hasattr(effective_from, "date"):
            effective_from = effective_from.date()
        effective_to = row.get("DateTo")
        if effective_to and hasattr(effective_to, "date"):
            effective_to = effective_to.date()
        return {
            "property": prop,
            "name": (row.get("Name") or f"Season {row['ID']}")[:128],
            "currency": currency,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "is_active": True,
            "notes": (row.get("Notes") or "").strip(),
            "inclusion": (row.get("Inclusion") or "").strip(),
        }

    def _process_row(self, row: dict[str, Any], report: LoadReport) -> None:
        super()._process_row(row, report)
        legacy_id = row.get(self.legacy_pk_column)
        if legacy_id is None:
            return
        plan = RatePlan.objects.filter(legacy_id=str(legacy_id)).first()
        if plan is None:
            return
        RateCard.objects.update_or_create(
            legacy_id=str(legacy_id),
            defaults={
                "plan": plan,
                "name": plan.name[:128],
                "min_nights": 1,
                "sort_order": 0,
                "is_active": True,
            },
        )


class RateRuleLoader(BaseLoader):
    """VillaSeasonRate -> RateRule on the season's default RateCard.

    Notes:
    - Skip `IsExTra=1` rows (extras, not base rates).
    - priority = legacy ID so EXCLUDE constraint never trips on overlaps.
    - max_party falls back to the property's capacity when PartySize is null.
    """

    name = "rate_rule"
    target_model = RateRule
    legacy_pk_column = "ID"
    legacy_query = (
        "SELECT ID, VillaId, SeasonId, CurrencyId, FromDate, ToDate, "
        "PartySize, IsPOA, WeeklyPrice, NightlyPrice, Price, "
        "PriceType, IsExTra, IsApprove, IsAvailable, Description "
        "FROM VillaSeasonRate WHERE DeletedAt IS NULL AND IsExTra <> 1"
    )

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        card = RateCard.objects.filter(legacy_id=str(row.get("SeasonId") or "")).first()
        if card is None:
            return None
        date_from = row.get("FromDate")
        date_to = row.get("ToDate")
        if date_from is None or date_to is None:
            return None
        if hasattr(date_from, "date"):
            date_from = date_from.date()
        if hasattr(date_to, "date"):
            date_to = date_to.date()
        if date_to <= date_from:
            # Zero-length / inverted ranges violate raterule_date_from_lt_date_to.
            return None
        party = int(row.get("PartySize") or 0)
        if party <= 0:
            # Fall back to property capacity for the upper bound.
            cap = card.plan.property.capacity.guests or 1
            min_party, max_party = 1, max(cap, 1)
        else:
            min_party, max_party = party, party
        nightly = _to_decimal(row.get("NightlyPrice"))
        weekly = _to_decimal(row.get("WeeklyPrice"))
        price = _to_decimal(row.get("Price"))
        is_poa = bool(row.get("IsPOA"))
        if not (nightly or weekly or price or is_poa):
            return None
        # If only Price is set, treat it as nightly.
        if nightly is None and weekly is None and price is not None:
            nightly = price
        if is_poa:
            # POA wins over any numeric price: raterule_poa_excludes_price
            # forbids both, and a hidden "on application" price must never
            # resurface as a concrete rate.
            nightly = None
            weekly = None
        return {
            "card": card,
            "date_from": date_from,
            "date_to": date_to,
            "min_party": min_party,
            "max_party": max_party,
            "priority": min(int(row["ID"]) % 65535, 65535),
            "nightly": nightly,
            "weekly": weekly,
            "is_poa": is_poa,
            "is_approved": bool(row.get("IsApprove")),
            "notes": (row.get("Description") or "").strip(),
        }
