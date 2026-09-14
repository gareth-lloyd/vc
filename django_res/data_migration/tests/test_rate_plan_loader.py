"""RatePlanLoader: one RatePlan per (villa, resolved currency) — GAP-110 U0a.

Legacy `VillaSeason` rows are year/era buckets whose dates were never a
pricing input, so the loader regroups them: every live, priced season of a
villa that resolves to the same currency lands on ONE regime plan keyed
`villa:<VillaId>:<CODE>`. Currency resolution keeps the GAP-014 step-0 chain:
season's own non-NULL rows → villa's other rows → settings → EUR — never the
ordering-dependent `Currency.objects.first()`.
"""

from __future__ import annotations

from datetime import date

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.pricing import (
    RatePlanLoader,
    plan_legacy_id,
    resolve_season_currency,
)
from pricing.models.currency import Currency
from pricing.models.rate import RatePlan
from properties.enums import PriceBasis
from properties.models import PropertyService
from properties.models.geo import Country, Region
from properties.models.property import Property
from properties.models.settings import PropertySettings


@pytest.fixture
def loaded_property(db: None) -> Property:
    country = Country.objects.get(iso2="GB")
    region = Region.objects.create(country=country, name="Cornwall", slug="cornwall")
    return Property.objects.create(
        name="P",
        display_name="P",
        slug="p",
        region=region,
        legacy_id="900",
    )


@pytest.fixture
def eur(db: None) -> Currency:
    return Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")


@pytest.fixture
def gbp(db: None) -> Currency:
    return Currency.objects.create(code="GBP", name="Pound sterling", symbol="£", legacy_id="1")


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ID": 1,
        "Name": "High Season",
        "VillaId": 900,
        "Notes": None,
        "Inclusion": None,
        "CurrencyId": None,
        "VillaCurrencyId": None,
        "DateFrom": date(2025, 1, 1),
        "DateTo": date(2025, 12, 31),
        "RateCount": 1,
    }
    base.update(overrides)
    return base


def _load(*rows: dict[str, object]) -> LoadReport:
    report = LoadReport(loader="rate_plan")
    RatePlanLoader()._load_rows(list(rows), report)
    return report


# --- currency resolution (GAP-014 step 0, unchanged chain) -------------------


@pytest.mark.django_db
def test_season_currency_used_when_present(
    loaded_property: Property, gbp: Currency, eur: Currency
) -> None:
    assert resolve_season_currency(_row(CurrencyId=1, VillaCurrencyId=3), loaded_property) == gbp


@pytest.mark.django_db
def test_null_season_currency_infers_from_villa_rows(
    loaded_property: Property, gbp: Currency, eur: Currency
) -> None:
    assert resolve_season_currency(_row(CurrencyId=None, VillaCurrencyId=1), loaded_property) == gbp


@pytest.mark.django_db
def test_null_currencies_fall_back_to_settings(
    loaded_property: Property, gbp: Currency, eur: Currency
) -> None:
    PropertySettings.objects.create(property=loaded_property, currency=gbp)
    assert resolve_season_currency(_row(), loaded_property) == gbp


@pytest.mark.django_db
def test_null_currencies_terminal_default_is_eur_not_first_row(
    loaded_property: Property,
) -> None:
    # AUD sorts (and was created) first — `.first()` would pick it.
    Currency.objects.create(code="AUD", name="Australian dollar", symbol="$", legacy_id="9")
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    assert resolve_season_currency(_row(), loaded_property) == eur


@pytest.mark.django_db
def test_row_skipped_when_nothing_resolves(loaded_property: Property, gbp: Currency) -> None:
    # No EUR row, no settings, no usable legacy currency → skip, don't guess.
    assert resolve_season_currency(_row(), loaded_property) is None
    report = _load(_row())
    assert report.skipped == 1
    assert not RatePlan.objects.exists()


@pytest.mark.django_db
def test_fallback_ignores_previously_loaded_plans(
    loaded_property: Property, gbp: Currency, eur: Currency
) -> None:
    """Re-run convergence: the fallback must not read the RatePlan table this
    loader populates. A run-1 mis-stamp (EUR) would otherwise re-resolve from
    itself forever; a since-fixed PropertySettings (GBP) must win instead."""
    RatePlan.objects.create(
        property=loaded_property,
        name="EUR rates",
        currency=eur,  # the run-1 stamp the re-run must NOT echo
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 12, 31),
        legacy_id="villa:900:EUR",
    )
    PropertySettings.objects.create(property=loaded_property, currency=gbp)
    assert resolve_season_currency(_row(), loaded_property) == gbp


# --- regrouping: one plan per (villa, currency) -----------------------------


@pytest.mark.django_db
def test_two_seasons_one_currency_merge_into_one_plan(
    loaded_property: Property, eur: Currency
) -> None:
    report = _load(
        _row(ID=1, Name="2024 rates", CurrencyId=3, Notes="Owner-negotiated."),
        _row(
            ID=2,
            Name="2025 rates",
            CurrencyId=3,
            Notes="Re-priced Jan.",
            DateFrom=date(2026, 1, 1),
            DateTo=date(2026, 12, 31),
        ),
    )

    assert report.created == 1 and report.updated == 0 and report.skipped == 0
    plan = RatePlan.objects.get()
    assert plan.legacy_id == plan_legacy_id(900, "EUR") == "villa:900:EUR"
    assert plan.property == loaded_property
    assert plan.currency == eur
    assert plan.name == "EUR rates"
    assert plan.is_active is True
    assert plan.price_basis == PriceBasis.GROSS
    # Merged seasons stay traceable: "id — name" per season + every Notes blurb.
    assert "1 — 2024 rates" in plan.notes
    assert "2 — 2025 rates" in plan.notes
    assert "Owner-negotiated." in plan.notes
    assert "Re-priced Jan." in plan.notes
    # Interim envelope (dropped in U6a): merged min/max of the live windows.
    assert plan.effective_from == date(2025, 1, 1)
    assert plan.effective_to == date(2026, 12, 31)


@pytest.mark.django_db
def test_single_season_keeps_its_name_and_notes(loaded_property: Property, eur: Currency) -> None:
    _load(_row(ID=1, Name="High Season", CurrencyId=3, Notes="Owner-negotiated."))
    plan = RatePlan.objects.get()
    assert plan.name == "High Season"
    assert plan.notes == "Owner-negotiated."


@pytest.mark.django_db
def test_two_currencies_make_two_plans(
    loaded_property: Property, eur: Currency, gbp: Currency
) -> None:
    report = _load(_row(ID=1, CurrencyId=3), _row(ID=2, CurrencyId=1))
    assert report.created == 2
    assert set(RatePlan.objects.values_list("legacy_id", flat=True)) == {
        "villa:900:EUR",
        "villa:900:GBP",
    }


@pytest.mark.django_db
def test_two_villas_make_two_plans(loaded_property: Property, eur: Currency) -> None:
    Property.objects.create(
        name="Q",
        display_name="Q",
        slug="q",
        region=loaded_property.region,
        legacy_id="901",
    )
    report = _load(_row(ID=1, VillaId=900, CurrencyId=3), _row(ID=2, VillaId=901, CurrencyId=3))
    assert report.created == 2
    assert set(RatePlan.objects.values_list("legacy_id", flat=True)) == {
        "villa:900:EUR",
        "villa:901:EUR",
    }


@pytest.mark.django_db
def test_rerun_updates_in_place(loaded_property: Property, eur: Currency) -> None:
    first = _load(_row(ID=1, CurrencyId=3), _row(ID=2, CurrencyId=3))
    second = _load(_row(ID=1, CurrencyId=3), _row(ID=2, CurrencyId=3, Name="Renamed"))
    assert (first.created, first.updated) == (1, 0)
    assert (second.created, second.updated) == (0, 1)
    plan = RatePlan.objects.get()
    assert "2 — Renamed" in plan.notes


@pytest.mark.django_db
def test_rate_less_season_makes_no_plan(loaded_property: Property, eur: Currency) -> None:
    """A season with no live priced rate rows is not a regime: the query
    reports `RateCount=0` and the loader records a skip rather than minting an
    empty plan (17 such seasons in the 2026-06 dump)."""
    report = _load(_row(ID=1, CurrencyId=3, RateCount=0))
    assert report.skipped == 1
    assert not RatePlan.objects.exists()


@pytest.mark.django_db
def test_unknown_villa_is_skipped(loaded_property: Property, eur: Currency) -> None:
    report = _load(_row(ID=1, VillaId=999999, CurrencyId=3))
    assert report.skipped == 1
    assert not RatePlan.objects.exists()


@pytest.mark.django_db
def test_no_live_window_leaves_envelope_open(loaded_property: Property, eur: Currency) -> None:
    _load(_row(ID=1, CurrencyId=3, DateFrom=None, DateTo=None))
    plan = RatePlan.objects.get()
    assert plan.effective_from == date(2020, 1, 1)
    assert plan.effective_to is None


@pytest.mark.django_db
def test_rerun_purges_pre_regroup_season_keyed_plans(
    loaded_property: Property, eur: Currency
) -> None:
    """A DB loaded before GAP-110 holds plans keyed by season id (and services
    keyed `<id>:svc`); an in-place re-run must retire them, or they'd sit
    beside the regime plan as a second active plan in the same currency."""
    RatePlan.objects.create(
        property=loaded_property,
        name="High Season",
        currency=eur,
        effective_from=date(2025, 1, 1),
        legacy_id="1",
    )
    PropertyService.objects.create(
        property=loaded_property,
        name="Included services",
        copy="Chef.",
        applies_from=date(2025, 6, 1),
        applies_to=date(2025, 8, 31),
        legacy_id="1:svc",
    )
    # A staff-made plan in another regime bucket (NET) survives untouched. An
    # active staff plan in the *same* bucket as the loader's would trip
    # `rateplan_one_active_per_regime` — the operator resolves that by hand.
    staff_plan = RatePlan.objects.create(
        property=loaded_property,
        name="Staff plan",
        currency=eur,
        price_basis=PriceBasis.NET,
        effective_from=date(2025, 1, 1),
    )
    _load(_row(ID=1, CurrencyId=3, Inclusion="Chef."))

    assert set(RatePlan.objects.values_list("legacy_id", flat=True)) == {"villa:900:EUR", None}
    assert RatePlan.objects.filter(pk=staff_plan.pk).exists()
    assert list(PropertyService.objects.values_list("legacy_id", flat=True)) == ["season:1:svc"]


@pytest.mark.django_db
def test_inverted_live_window_is_ignored(loaded_property: Property, eur: Currency) -> None:
    """Junk `VillaSeasonDates` (to before from) must neither band a service
    (the from<=to CHECK would roll the whole plan back) nor set the envelope."""
    _load(
        _row(
            ID=1,
            CurrencyId=3,
            Inclusion="Chef.",
            DateFrom=date(2025, 9, 1),
            DateTo=date(2025, 6, 1),
        ),
        _row(ID=2, CurrencyId=3, DateFrom=date(2026, 1, 1), DateTo=date(2026, 12, 31)),
    )
    plan = RatePlan.objects.get()
    assert (plan.effective_from, plan.effective_to) == (date(2026, 1, 1), date(2026, 12, 31))
    assert not PropertyService.objects.exists()


@pytest.mark.django_db
def test_failing_group_is_isolated_and_reported(
    loaded_property: Property, eur: Currency, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One bad (villa, currency) group is recorded under its plan key and
    rolled back to its savepoint; sibling groups still land."""
    Property.objects.create(
        name="Q", display_name="Q", slug="q", region=loaded_property.region, legacy_id="901"
    )
    real = RatePlanLoader._load_group

    def boom(self: RatePlanLoader, prop: Property, *args: object, **kw: object) -> bool:
        created = real(self, prop, *args, **kw)  # type: ignore[arg-type]
        if prop.legacy_id == "901":
            raise RuntimeError("simulated write failure")
        return created

    monkeypatch.setattr(RatePlanLoader, "_load_group", boom)
    report = _load(_row(ID=1, VillaId=900, CurrencyId=3), _row(ID=2, VillaId=901, CurrencyId=3))

    assert report.created == 1
    assert [key for key, _ in report.errors] == ["villa:901:EUR"]
    assert list(RatePlan.objects.values_list("legacy_id", flat=True)) == ["villa:900:EUR"]


def test_apply_since_is_a_no_op() -> None:
    """Regrouping is a function of the villa's whole season set, so a `--since`
    delta would merge against seasons it can't see: every pass is a full load."""
    loader = RatePlanLoader(since="2026-01-01T00:00:00")
    assert loader._apply_since("SELECT 1") == "SELECT 1"


# --- GAP-037: Inclusion → PropertyService per season ------------------------


@pytest.mark.django_db
def test_inclusion_emits_one_property_service_per_season(
    loaded_property: Property, eur: Currency
) -> None:
    """Each carrying season keeps its own date-banded PropertyService (keyed
    `season:<ID>:svc`, dated by the season's live window), idempotent across
    re-runs even though the seasons share one plan."""
    rows = (
        _row(
            ID=1,
            CurrencyId=3,
            Inclusion="Private chef included.",
            DateFrom=date(2025, 6, 1),
            DateTo=date(2025, 8, 31),
        ),
        _row(
            ID=2,
            CurrencyId=3,
            Inclusion="Boat included.",
            DateFrom=date(2026, 6, 1),
            DateTo=date(2026, 8, 31),
        ),
    )
    _load(*rows)
    _load(*rows)  # re-run: still one per season

    assert RatePlan.objects.count() == 1
    assert PropertyService.objects.count() == 2
    svc = PropertyService.objects.get(legacy_id="season:1:svc")
    assert svc.property == loaded_property
    assert svc.name == "Included services"
    assert svc.copy == "Private chef included."
    assert svc.applies_from == date(2025, 6, 1)
    assert svc.applies_to == date(2025, 8, 31)
    assert svc.is_active is True
    assert PropertyService.objects.get(legacy_id="season:2:svc").copy == "Boat included."


@pytest.mark.django_db
def test_inclusion_without_live_window_makes_no_service(
    loaded_property: Property, eur: Currency
) -> None:
    """A season whose every VillaSeasonDates row is soft-deleted has no window
    to band the service on — skip it rather than invent an open-ended one."""
    _load(_row(ID=1, CurrencyId=3, Inclusion="Chef included.", DateFrom=None, DateTo=None))
    assert RatePlan.objects.count() == 1
    assert not PropertyService.objects.exists()


@pytest.mark.django_db
def test_no_service_when_plan_unresolved(loaded_property: Property, eur: Currency) -> None:
    """An Inclusion on a season whose plan never materialises (villa doesn't
    resolve) must not leave an orphan PropertyService."""
    _load(_row(ID=3, VillaId=999999, CurrencyId=3, Inclusion="Chef included."))
    assert not PropertyService.objects.exists()


@pytest.mark.django_db
def test_no_service_when_inclusion_blank(loaded_property: Property, eur: Currency) -> None:
    _load(_row(ID=2, CurrencyId=3, Inclusion=None))
    assert not PropertyService.objects.exists()


@pytest.mark.django_db
def test_plan_carries_notes_not_inclusion(loaded_property: Property, eur: Currency) -> None:
    """GAP-037: inclusion never lands on RatePlan; operator notes do."""
    _load(_row(CurrencyId=3, Notes="Owner-negotiated.", Inclusion="Private chef included."))
    plan = RatePlan.objects.get()
    assert plan.notes == "Owner-negotiated."
    assert "chef" not in plan.notes.lower()
