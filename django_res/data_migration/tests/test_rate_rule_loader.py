from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.pricing import RateRuleLoader
from pricing.models.currency import Currency
from pricing.models.rate import RateCard, RatePeriod, RatePlan, RateRule
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


@pytest.mark.django_db
def test_transform_occupancy_band_uses_range_and_price(loaded_card: RateCard) -> None:
    """An occupancy band row carries its (from, to) party range and its own
    weekly/nightly price straight through to the RateRule kwargs."""
    kwargs = RateRuleLoader().transform(
        _row(_occ_band=(2, 4), WeeklyPrice=Decimal("500"), NightlyPrice=Decimal("71.43")),
    )
    assert kwargs is not None
    assert (kwargs["min_party"], kwargs["max_party"]) == (2, 4)
    assert kwargs["weekly"] == Decimal("500")
    assert kwargs["nightly"] == Decimal("71.43")


@pytest.mark.django_db
def test_transform_occupancy_band_open_top_clamps_to_capacity(loaded_card: RateCard) -> None:
    """An open-topped band (from, None) — the above-max gap fallback — clamps to
    the property capacity."""
    kwargs = RateRuleLoader().transform(_row(_occ_band=(6, None), WeeklyPrice=Decimal("700")))
    assert kwargs is not None
    assert (kwargs["min_party"], kwargs["max_party"]) == (6, 8)


@pytest.mark.django_db
def test_transform_party_intervals_override_occ_band(loaded_card: RateCard) -> None:
    """A resolver party-clip (`_party_intervals`) wins over the raw band range."""
    kwargs = RateRuleLoader().transform(
        _row(_occ_band=(2, 8), _party_intervals=[(5, 8)], WeeklyPrice=Decimal("500")),
    )
    assert kwargs is not None
    assert (kwargs["min_party"], kwargs["max_party"]) == (5, 8)


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
def test_load_rows_expands_occupancy_bands_with_gap_fallback(loaded_card: RateCard) -> None:
    """A banded parent (bands 2-4/5-6, cap 8, base weekly) + a simple rate ->
    band rules (`occ-*`) + base-weekly fallback rules on the uncovered party
    gaps (1 and 7-8) + the simple rule, all disjoint under the EXCLUDE
    constraint."""
    rows = [
        _row(
            ID=1,
            FromDate=date(2025, 6, 1),
            ToDate=date(2025, 6, 14),
            IsOccupationPrice=True,
            OccId=101,
            OccupencyFrom=2,
            OccupencyTo=4,
            OccupencyPrice=Decimal("500"),
        ),
        _row(
            ID=1,
            FromDate=date(2025, 6, 1),
            ToDate=date(2025, 6, 14),
            IsOccupationPrice=True,
            OccId=102,
            OccupencyFrom=5,
            OccupencyTo=6,
            OccupencyPrice=Decimal("700"),
        ),
        _row(
            ID=2, FromDate=date(2025, 6, 20), ToDate=date(2025, 6, 27), WeeklyPrice=Decimal("900")
        ),
    ]
    loader = RateRuleLoader()
    report = LoadReport(loader="rate_rule")
    loader._load_rows(rows, report)

    assert report.errors == []
    rules = {r.legacy_id: r for r in RateRule.objects.all()}
    assert set(rules) == {"occ-101", "occ-102", "occ-fb-1-0", "occ-fb-1-1", "2"}
    assert (rules["occ-101"].min_party, rules["occ-101"].max_party) == (2, 4)
    assert rules["occ-101"].weekly == Decimal("500")
    assert (rules["occ-102"].min_party, rules["occ-102"].max_party) == (5, 6)
    # Below-min gap (guest 1) and above-max gap (7-8, capacity-clamped) get the
    # parent's base weekly price — full legacy parity.
    assert (rules["occ-fb-1-0"].min_party, rules["occ-fb-1-0"].max_party) == (1, 1)
    assert rules["occ-fb-1-0"].weekly == Decimal("1000")
    assert (rules["occ-fb-1-1"].min_party, rules["occ-fb-1-1"].max_party) == (7, 8)
    assert rules["occ-fb-1-1"].weekly == Decimal("1000")

    # Full-replace idempotency: a second run reproduces the identical row set.
    second = LoadReport(loader="rate_rule")
    loader._load_rows(rows, second)
    assert second.errors == []
    assert RateRule.objects.count() == 5


@pytest.mark.django_db
def test_load_rows_null_bound_band_does_not_abort_load(loaded_card: RateCard) -> None:
    """A null-bound occupancy child would `None <= int` crash in the resolver
    if coerced; `_prepare_occupancy_rows` drops it so the whole load survives
    and the parent fallback covers its party range."""
    rows = [
        _row(
            ID=1,
            FromDate=date(2025, 6, 1),
            ToDate=date(2025, 6, 14),
            IsOccupationPrice=True,
            OccId=101,
            OccupencyFrom=2,
            OccupencyTo=4,
            OccupencyPrice=Decimal("500"),
        ),
        _row(
            ID=1,
            FromDate=date(2025, 6, 1),
            ToDate=date(2025, 6, 14),
            IsOccupationPrice=True,
            OccId=102,
            OccupencyFrom=None,
            OccupencyTo=None,
            OccupencyPrice=Decimal("700"),
        ),
    ]
    loader = RateRuleLoader()
    report = LoadReport(loader="rate_rule")
    loader._load_rows(rows, report)

    assert report.errors == []
    rules = {r.legacy_id: r for r in RateRule.objects.all()}
    assert set(rules) == {"occ-101", "occ-fb-1-0", "occ-fb-1-1"}
    # Dropped band (5,6)'s range is folded into the above gap fallback (5-8).
    assert (rules["occ-fb-1-1"].min_party, rules["occ-fb-1-1"].max_party) == (5, 8)


@pytest.mark.django_db
def test_load_rows_creates_disjoint_periods_for_overlapping_party_rows(
    loaded_card: RateCard,
) -> None:
    """Two party-disjoint but date-overlapping legacy rows both survive the
    resolver (no party conflict), so the `save()` shim would stamp them with
    overlapping per-exact-date periods ([Jun1-Jun20] and [Jun1-Jun10]). The
    loader must instead segment the plan onto a disjoint date axis (fragmenting
    the wider rule) — the invariant Unit 9's periods-disjoint EXCLUDE enforces."""
    rows = [
        _row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 20), PartySize=2),
        _row(ID=2, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 10), PartySize=5),
    ]
    loader = RateRuleLoader()
    loader._load_rows(rows, LoadReport(loader="rate_rule"))

    periods = list(
        RatePeriod.objects.filter(plan=loaded_card.plan).order_by("date_from", "date_to")
    )
    spans = [(p.date_from, p.date_to) for p in periods]
    # Disjoint: no two periods overlap (inclusive dates).
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            assert not (spans[i][0] <= spans[j][1] and spans[j][0] <= spans[i][1]), spans
    # Every loaded rule hangs off a period (none left orphaned).
    rules = RateRule.objects.filter(card__plan=loaded_card.plan)
    assert rules.exists()
    assert all(r.period_id is not None for r in rules)
    # The wider rule was fragmented across the segment boundary at Jun 10/11.
    assert spans == [(date(2025, 6, 1), date(2025, 6, 10)), (date(2025, 6, 11), date(2025, 6, 20))]


@pytest.mark.django_db
def test_load_rows_periods_stable_and_disjoint_across_reruns(loaded_card: RateCard) -> None:
    """Full-reload idempotency for the period axis: a second load of the same
    rows reproduces the identical disjoint period set with no stale-period
    accumulation (the reset + rule-less sweep must not leave orphans behind)."""

    def rows() -> list[dict[str, object]]:
        return [
            _row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 20), PartySize=2),
            _row(ID=2, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 10), PartySize=5),
        ]

    loader = RateRuleLoader()
    loader._load_rows(rows(), LoadReport(loader="rate_rule"))
    first_spans = sorted(RatePeriod.objects.values_list("date_from", "date_to"))
    first_period_count = RatePeriod.objects.count()

    loader._load_rows(rows(), LoadReport(loader="rate_rule"))
    second_spans = sorted(RatePeriod.objects.values_list("date_from", "date_to"))

    assert second_spans == first_spans  # stable — no drift
    assert RatePeriod.objects.count() == first_period_count  # no stale accumulation
    assert all(r.period_id is not None for r in RateRule.objects.all())


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
