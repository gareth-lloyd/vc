"""GAP-014 step-0 currency audit.

Pricing in the rate plan's own currency makes migrated `RatePlan.currency`
customer-facing truth, so before the engine change ships, every plan whose
legacy season had only NULL/0 `CurrencyId` rows must be accounted for:

* resolved via the villa's other non-NULL rate rows or the settings chain → OK;
* resolved via the terminal EUR default → **listed for manual sign-off**
  (informational, not a blocker);
* loaded currency disagreeing with what the loader would resolve now →
  **BLOCKER** (re-run the pricing loaders before shipping rate-card-currency
  pricing).

Also prints the currently-bookable currency mix (active plans covering today
or later), which is what determines the practical severity of mixed-currency
inventory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from core.console import render_table
from data_migration.legacy_db import legacy_cursor, rows_as_dicts
from data_migration.loaders.pricing import PLAN_LEGACY_PREFIX, VILLA_CURRENCY_SUBSELECT
from pricing.models.currency import Currency
from pricing.models.rate import RatePlan
from pricing.services.currency import default_currency, settings_currency
from properties.models.property import Property

# Seasons whose own rate rows carry no usable currency, plus the villa-level
# inference the loader applies (the villa's most recent non-NULL row).
_AFFECTED_SEASONS_QUERY = (
    "SELECT s.ID, s.VillaId, "
    f"{VILLA_CURRENCY_SUBSELECT} AS VillaCurrencyId "
    "FROM VillaSeason s WHERE s.DeletedAt IS NULL AND NOT EXISTS ("
    " SELECT 1 FROM VillaSeasonRate r"
    " WHERE r.SeasonId = s.ID AND r.CurrencyId IS NOT NULL AND r.CurrencyId <> 0"
    " AND r.DeletedAt IS NULL)"
)


@dataclass
class AuditResult:
    rows: list[tuple[str, str, str, str, str]] = field(default_factory=list)
    eur_defaults: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    unloaded: int = 0


def _expected_resolution(prop: Property, villa_currency_id: Any) -> tuple[str, Currency | None]:
    """(rule label, currency) the loader chain would resolve for this villa now."""
    if villa_currency_id:
        villa_currency = Currency.objects.filter(legacy_id=str(villa_currency_id)).first()
        if villa_currency is not None:
            return "villa-rates", villa_currency
    # Same helper the loader's fallback uses (settings chain incl. the
    # group fallback) so the audit can never drift from the chain it audits.
    configured = settings_currency(prop)
    if configured is not None:
        return "settings", configured
    return "eur-default", default_currency()


def audit_null_currency_seasons(rows: list[dict[str, Any]]) -> AuditResult:
    """Compare each NULL-currency season's villa regime plans against the
    loader chain.

    GAP-110: a season no longer has a plan of its own — its rows land on the
    villa's `villa:<VillaId>:<CODE>` regime plan for the currency the chain
    resolves. So the question becomes: does that plan exist? A villa with
    regime plans but none in the expected currency was loaded under the wrong
    currency (BLOCKER); a villa with no regime plan at all is unloaded.
    """
    result = AuditResult()
    for row in rows:
        season_id = str(row["ID"])
        villa_id = str(row.get("VillaId") or "")
        plans = list(
            RatePlan.objects.filter(legacy_id__startswith=f"{PLAN_LEGACY_PREFIX}{villa_id}:")
            .select_related("currency", "property")
            .order_by("currency__code")
        )
        if not plans:
            result.unloaded += 1
            continue
        prop = plans[0].property
        rule, expected = _expected_resolution(prop, row.get("VillaCurrencyId"))
        loaded_codes = "/".join(p.currency.code for p in plans)
        ok = expected is not None and any(p.currency_id == expected.pk for p in plans)
        if not ok:
            result.blockers.append(
                f"season {season_id} ({prop.name}): loaded {loaded_codes}, "
                f"loader would resolve {expected.code if expected else 'nothing'} via {rule}"
            )
        elif rule == "eur-default":
            result.eur_defaults.append(f"season {season_id} — {prop.name}")
        result.rows.append(
            (season_id, prop.name[:40], rule, loaded_codes, "OK" if ok else "BLOCKER")
        )
    return result


def bookable_currency_mix() -> list[tuple[str, int, int]]:
    """(currency, plans, properties) for active plans with an active period
    ending today or later (GAP-110: periods, not the plan, date the regime)."""
    qs = (
        RatePlan.objects.filter(
            is_active=True, periods__is_active=True, periods__date_to__gte=date.today()
        )
        .values("currency__code")
        .annotate(plans=Count("pk", distinct=True), properties=Count("property", distinct=True))
        .order_by("-properties")
    )
    return [(r["currency__code"], r["plans"], r["properties"]) for r in qs]


class Command(BaseCommand):
    help = "Audit migrated RatePlan currencies for the NULL-CurrencyId legacy cohort (GAP-014)."

    def handle(self, *args: Any, **options: Any) -> None:
        with legacy_cursor() as cursor:
            cursor.execute(_AFFECTED_SEASONS_QUERY)
            rows = list(rows_as_dicts(cursor))

        result = audit_null_currency_seasons(rows)

        self.stdout.write(f"{len(rows)} legacy season(s) with only NULL/0 CurrencyId rows\n")
        if result.rows:
            header = ("season", "property", "rule", "loaded", "status")
            self.stdout.write(render_table(header, result.rows))
        if result.unloaded:
            self.stdout.write(
                f"{result.unloaded} affected season(s) have no loaded RatePlan "
                "(skipped by the loader — expected for villas missing from Property)."
            )

        if result.eur_defaults:
            self.stdout.write(
                f"\n{len(result.eur_defaults)} plan(s) resolved by the terminal EUR "
                "default — sign these off manually:"
            )
            for entry in result.eur_defaults:
                self.stdout.write(f"  - {entry}")
        else:
            self.stdout.write("\nNo plans needed the terminal EUR default.")

        mix = bookable_currency_mix()
        self.stdout.write("\nCurrently-bookable currency mix (active plans covering today+):")
        self.stdout.write(render_table(("currency", "plans", "properties"), mix))

        if result.blockers:
            raise CommandError(
                f"{len(result.blockers)} currency mismatch(es) — re-run the pricing "
                "loaders before pricing in the plan's currency:\n  " + "\n  ".join(result.blockers)
            )
