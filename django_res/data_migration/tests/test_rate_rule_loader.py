from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.pricing import RateRuleLoader
from pricing.models.currency import Currency
from pricing.models.rate import RateCard, RatePlan, RateRule
from properties.models.capacity import PropertyCapacity
from properties.models.geo import Country, Region
from properties.models.property import Property, PropertyCategory, PropertyGroup


@pytest.fixture
def loaded_property(db: None) -> Property:
    country = Country.objects.get(iso2="GB")
    region = Region.objects.create(country=country, name="Cornwall", slug="cornwall")
    cat = PropertyCategory.objects.create(name="Villa", slug="villa")
    group = PropertyGroup.objects.create(name="G")
    prop = Property.objects.create(
        name="P",
        display_name="P",
        slug="p",
        category=cat,
        group=group,
        region=region,
    )
    PropertyCapacity.objects.create(property=prop, guests=8)
    return prop


@pytest.fixture
def loaded_card(loaded_property: Property) -> RateCard:
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    plan = RatePlan.objects.create(
        property=loaded_property,
        name="High",
        currency=currency,
        effective_from=date(2025, 1, 1),
        legacy_id="42",
    )
    return RateCard.objects.create(plan=plan, name="default", legacy_id="42")


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ID": 1,
        "VillaId": None,
        "SeasonId": 42,
        "CurrencyId": 2,
        "FromDate": date(2025, 6, 1),
        "ToDate": date(2025, 6, 14),
        "PartySize": None,
        "IsPOA": False,
        "WeeklyPrice": Decimal("1000"),
        "NightlyPrice": None,
        "Price": None,
        "PriceType": 1,
        "IsExTra": False,
        "IsApprove": True,
        "IsAvailable": True,
        "Description": "Peak",
    }
    base.update(overrides)
    return base


@pytest.mark.django_db
def test_transform_uses_capacity_when_party_size_missing(loaded_card: RateCard) -> None:
    kwargs = RateRuleLoader().transform(_row(PartySize=None))
    assert kwargs is not None
    assert kwargs["min_party"] == 1
    assert kwargs["max_party"] == 8


@pytest.mark.django_db
def test_transform_skips_when_card_missing() -> None:
    assert RateRuleLoader().transform(_row(SeasonId=999)) is None


@pytest.mark.django_db
def test_transform_skips_inverted_date_range(loaded_card: RateCard) -> None:
    assert (
        RateRuleLoader().transform(
            _row(FromDate=date(2025, 6, 14), ToDate=date(2025, 6, 1)),
        )
        is None
    )


@pytest.mark.django_db
def test_transform_skips_row_with_no_price(loaded_card: RateCard) -> None:
    assert (
        RateRuleLoader().transform(
            _row(WeeklyPrice=None, NightlyPrice=None, Price=None, IsPOA=False),
        )
        is None
    )


@pytest.mark.django_db
def test_transform_treats_price_as_nightly_when_alone(loaded_card: RateCard) -> None:
    kwargs = RateRuleLoader().transform(
        _row(WeeklyPrice=None, NightlyPrice=None, Price=Decimal("250")),
    )
    assert kwargs is not None
    assert kwargs["nightly"] == Decimal("250")


@pytest.mark.django_db
def test_transform_keeps_poa_rows(loaded_card: RateCard) -> None:
    kwargs = RateRuleLoader().transform(
        _row(WeeklyPrice=None, NightlyPrice=None, Price=None, IsPOA=True),
    )
    assert kwargs is not None
    assert kwargs["is_poa"] is True


@pytest.mark.django_db
def test_transform_poa_drops_price(loaded_card: RateCard) -> None:
    """POA wins over a numeric price — raterule_poa_excludes_price forbids both."""
    kwargs = RateRuleLoader().transform(
        _row(WeeklyPrice=Decimal("1000"), NightlyPrice=Decimal("200"), IsPOA=True),
    )
    assert kwargs is not None
    assert kwargs["is_poa"] is True
    assert kwargs["nightly"] is None
    assert kwargs["weekly"] is None


@pytest.mark.django_db
def test_transform_skips_zero_length_range(loaded_card: RateCard) -> None:
    assert (
        RateRuleLoader().transform(
            _row(FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 1)),
        )
        is None
    )


@pytest.mark.django_db
def test_transform_party_intervals_prefers_first_valid(loaded_card: RateCard) -> None:
    """Resolver upper interval starts above capacity → fall back to the lower one."""
    kwargs = RateRuleLoader().transform(
        _row(PartySize=None, _party_intervals=[(9, None), (1, 3)]),
    )
    assert kwargs is not None
    assert (kwargs["min_party"], kwargs["max_party"]) == (1, 3)


@pytest.mark.django_db
def test_transform_party_intervals_unbounded_uses_capacity(loaded_card: RateCard) -> None:
    kwargs = RateRuleLoader().transform(
        _row(PartySize=None, _party_intervals=[(5, None)]),
    )
    assert kwargs is not None
    assert (kwargs["min_party"], kwargs["max_party"]) == (5, 8)


@pytest.mark.django_db
def test_transform_party_intervals_all_emptied_by_capacity(loaded_card: RateCard) -> None:
    assert RateRuleLoader().transform(_row(PartySize=None, _party_intervals=[(9, None)])) is None


def test_apply_since_is_a_noop() -> None:
    """Overlap resolution needs the whole season's row set — no `--since` delta."""
    loader = RateRuleLoader(since="2025-01-01T00:00:00")
    assert loader._apply_since(loader.legacy_query) == loader.legacy_query


@pytest.mark.django_db
def test_load_rows_double_run_converges(loaded_card: RateCard) -> None:
    def rows() -> list[dict[str, object]]:
        return [
            _row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 8)),
            _row(ID=2, FromDate=date(2025, 6, 8), ToDate=date(2025, 6, 15)),
        ]

    loader = RateRuleLoader()
    first = LoadReport(loader="rate_rule")
    loader._load_rows(rows(), first)
    assert (first.created, first.updated) == (2, 0)
    assert first.errors == []

    # Full-replace semantics: every run purges and reinserts, so the second
    # run also reports creates — but the resulting row set is identical.
    second = LoadReport(loader="rate_rule")
    loader._load_rows(rows(), second)
    assert (second.created, second.updated) == (2, 0)
    assert second.errors == []
    assert RateRule.objects.count() == 2
    # Boundary trim applied: inclusive ranges no longer share Jun 8.
    assert RateRule.objects.get(legacy_id="1").date_to == date(2025, 6, 7)


@pytest.mark.django_db
def test_load_rows_purge_deletes_newly_dropped_row(loaded_card: RateCard) -> None:
    loader = RateRuleLoader()
    loader._load_rows(
        [
            _row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 8)),
            _row(ID=2, FromDate=date(2025, 6, 10), ToDate=date(2025, 6, 15)),
        ],
        LoadReport(loader="rate_rule"),
    )
    assert RateRule.objects.count() == 2

    # Legacy row 1 grew to fully cover row 2 → resolver drops 2; the purge
    # frees row 2's old span so row 1's expansion can't trip the EXCLUDE
    # constraint — convergence in one run, no report.errors.
    second = LoadReport(loader="rate_rule")
    loader._load_rows(
        [
            _row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 20)),
            _row(ID=2, FromDate=date(2025, 6, 10), ToDate=date(2025, 6, 15)),
        ],
        second,
    )
    assert second.errors == []
    assert list(RateRule.objects.values_list("legacy_id", flat=True)) == ["1"]
    rule = RateRule.objects.get(legacy_id="1")
    assert (rule.date_from, rule.date_to) == (date(2025, 6, 1), date(2025, 6, 20))


@pytest.mark.django_db
def test_load_rows_span_swap_converges(loaded_card: RateCard) -> None:
    """Two rows exchanging spans between dumps can never converge under
    in-place upserts (each update collides with the other's old span);
    purge-then-insert makes it a non-event."""
    loader = RateRuleLoader()
    loader._load_rows(
        [
            _row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 8)),
            _row(ID=2, FromDate=date(2025, 6, 10), ToDate=date(2025, 6, 15)),
        ],
        LoadReport(loader="rate_rule"),
    )

    second = LoadReport(loader="rate_rule")
    loader._load_rows(
        [
            _row(ID=1, FromDate=date(2025, 6, 10), ToDate=date(2025, 6, 15)),
            _row(ID=2, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 8)),
        ],
        second,
    )
    assert second.errors == []
    rule1 = RateRule.objects.get(legacy_id="1")
    rule2 = RateRule.objects.get(legacy_id="2")
    assert (rule1.date_from, rule1.date_to) == (date(2025, 6, 10), date(2025, 6, 15))
    assert (rule2.date_from, rule2.date_to) == (date(2025, 6, 1), date(2025, 6, 8))


@pytest.mark.django_db
def test_load_rows_purge_removes_vanished_season_rules(loaded_card: RateCard) -> None:
    loader = RateRuleLoader()
    loader._load_rows(
        [_row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 8))],
        LoadReport(loader="rate_rule"),
    )
    assert RateRule.objects.count() == 1

    # Season 42 disappears from the dump entirely — full reload purges its rules.
    loader._load_rows([], LoadReport(loader="rate_rule"))
    assert RateRule.objects.count() == 0


@pytest.mark.django_db
def test_load_rows_purge_spares_ui_rules(loaded_card: RateCard) -> None:
    """The purge is scoped to legacy_id-bearing rules; UI-created rows survive."""
    ui_rule = RateRule.objects.create(
        card=loaded_card,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
        min_party=1,
        max_party=8,
        weekly=Decimal("900"),
    )
    loader = RateRuleLoader()
    loader._load_rows(
        [_row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 8))],
        LoadReport(loader="rate_rule"),
    )
    assert RateRule.objects.filter(pk=ui_rule.pk).exists()
