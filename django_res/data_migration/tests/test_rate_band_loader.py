from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.pricing import RateBandLoader, _row_to_band
from pricing.models.currency import Currency
from pricing.models.rate import RateBand, RatePeriod, RatePlan
from properties.models.capacity import PropertyCapacity
from properties.models.geo import Country, Region
from properties.models.property import Property, PropertyCategory


@pytest.fixture
def loaded_property(db: None) -> Property:
    country = Country.objects.get(iso2="GB")
    region = Region.objects.create(country=country, name="Cornwall", slug="cornwall")
    cat = PropertyCategory.objects.create(name="Villa", slug="villa")
    prop = Property.objects.create(
        name="P",
        display_name="P",
        slug="p",
        category=cat,
        region=region,
    )
    PropertyCapacity.objects.create(property=prop, guests=8)
    return prop


@pytest.fixture
def loaded_plan(loaded_property: Property) -> RatePlan:
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    return RatePlan.objects.create(
        property=loaded_property,
        name="High",
        currency=currency,
        effective_from=date(2025, 1, 1),
        legacy_id="42",
    )


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
def test_row_to_band_uses_capacity_when_party_size_missing(loaded_plan: RatePlan) -> None:
    band = _row_to_band(_row(PartySize=None), loaded_plan)
    assert band is not None
    assert band.min_party == 1
    assert band.max_party == 8


@pytest.mark.django_db
def test_load_rows_skips_when_plan_missing(loaded_plan: RatePlan) -> None:
    """A row whose season has no loaded RatePlan is skipped, not loaded."""
    loader = RateBandLoader()
    report = LoadReport(loader="rate_rule")
    loader._load_rows([_row(SeasonId=999)], report)
    assert RateBand.objects.count() == 0
    assert report.skipped == 1


@pytest.mark.django_db
def test_row_to_band_skips_inverted_date_range(loaded_plan: RatePlan) -> None:
    assert (
        _row_to_band(
            _row(FromDate=date(2025, 6, 14), ToDate=date(2025, 6, 1)),
            loaded_plan,
        )
        is None
    )


@pytest.mark.django_db
def test_row_to_band_skips_row_with_no_price(loaded_plan: RatePlan) -> None:
    assert (
        _row_to_band(
            _row(WeeklyPrice=None, NightlyPrice=None, Price=None, IsPOA=False),
            loaded_plan,
        )
        is None
    )


@pytest.mark.django_db
def test_row_to_band_treats_price_as_nightly_when_alone(loaded_plan: RatePlan) -> None:
    band = _row_to_band(
        _row(WeeklyPrice=None, NightlyPrice=None, Price=Decimal("250")),
        loaded_plan,
    )
    assert band is not None
    assert band.nightly == Decimal("250")


@pytest.mark.django_db
def test_row_to_band_keeps_poa_rows(loaded_plan: RatePlan) -> None:
    band = _row_to_band(
        _row(WeeklyPrice=None, NightlyPrice=None, Price=None, IsPOA=True),
        loaded_plan,
    )
    assert band is not None
    assert band.is_poa is True


@pytest.mark.django_db
def test_row_to_band_poa_drops_price(loaded_plan: RatePlan) -> None:
    """POA wins over a numeric price — raterule_poa_excludes_price forbids both."""
    band = _row_to_band(
        _row(WeeklyPrice=Decimal("1000"), NightlyPrice=Decimal("200"), IsPOA=True),
        loaded_plan,
    )
    assert band is not None
    assert band.is_poa is True
    assert band.nightly is None
    assert band.weekly is None


@pytest.mark.django_db
def test_row_to_band_skips_zero_length_range(loaded_plan: RatePlan) -> None:
    assert (
        _row_to_band(
            _row(FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 1)),
            loaded_plan,
        )
        is None
    )


@pytest.mark.django_db
def test_row_to_band_occupancy_band_uses_range_and_price(loaded_plan: RatePlan) -> None:
    """An occupancy band row carries its (from, to) party range and its own
    weekly/nightly price straight through to the band."""
    band = _row_to_band(
        _row(_occ_band=(2, 4), WeeklyPrice=Decimal("500"), NightlyPrice=Decimal("71.43")),
        loaded_plan,
    )
    assert band is not None
    assert (band.min_party, band.max_party) == (2, 4)
    assert band.weekly == Decimal("500")
    assert band.nightly == Decimal("71.43")


@pytest.mark.django_db
def test_row_to_band_occupancy_band_open_top_clamps_to_capacity(loaded_plan: RatePlan) -> None:
    """An open-topped band (from, None) — the above-max gap fallback — clamps to
    the property capacity."""
    band = _row_to_band(_row(_occ_band=(6, None), WeeklyPrice=Decimal("700")), loaded_plan)
    assert band is not None
    assert (band.min_party, band.max_party) == (6, 8)


def test_apply_since_is_a_noop() -> None:
    """Overlap resolution needs the whole season's row set — no `--since` delta."""
    loader = RateBandLoader(since="2025-01-01T00:00:00")
    assert loader._apply_since(loader.legacy_query) == loader.legacy_query


@pytest.mark.django_db
def test_load_rows_double_run_converges(loaded_plan: RatePlan) -> None:
    def rows() -> list[dict[str, object]]:
        return [
            _row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 8)),
            _row(ID=2, FromDate=date(2025, 6, 8), ToDate=date(2025, 6, 15)),
        ]

    loader = RateBandLoader()
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
    assert RateBand.objects.count() == 2
    # Boundary trim applied: inclusive ranges no longer share Jun 8, so the
    # earlier rule's period ends Jun 7.
    assert RateBand.objects.get(legacy_id="1").period.date_to == date(2025, 6, 7)


@pytest.mark.django_db
def test_load_rows_purge_deletes_newly_dropped_row(loaded_plan: RatePlan) -> None:
    loader = RateBandLoader()
    loader._load_rows(
        [
            _row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 8)),
            _row(ID=2, FromDate=date(2025, 6, 10), ToDate=date(2025, 6, 15)),
        ],
        LoadReport(loader="rate_rule"),
    )
    assert RateBand.objects.count() == 2

    # Legacy row 1 grew to fully cover row 2 → the flattener fully shadows
    # 2 (shadowed_dropped, not the resolver's counter); the purge
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
    assert list(RateBand.objects.values_list("legacy_id", flat=True)) == ["1"]
    rule = RateBand.objects.get(legacy_id="1")
    assert (rule.period.date_from, rule.period.date_to) == (date(2025, 6, 1), date(2025, 6, 20))


@pytest.mark.django_db
def test_load_rows_span_swap_converges(loaded_plan: RatePlan) -> None:
    """Two rows exchanging spans between dumps can never converge under
    in-place upserts (each update collides with the other's old span);
    purge-then-insert makes it a non-event."""
    loader = RateBandLoader()
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
    rule1 = RateBand.objects.get(legacy_id="1")
    rule2 = RateBand.objects.get(legacy_id="2")
    assert (rule1.period.date_from, rule1.period.date_to) == (date(2025, 6, 10), date(2025, 6, 15))
    assert (rule2.period.date_from, rule2.period.date_to) == (date(2025, 6, 1), date(2025, 6, 8))


@pytest.mark.django_db
def test_load_rows_purge_removes_vanished_season_rules(loaded_plan: RatePlan) -> None:
    loader = RateBandLoader()
    loader._load_rows(
        [_row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 8))],
        LoadReport(loader="rate_rule"),
    )
    assert RateBand.objects.count() == 1

    # Season 42 disappears from the dump entirely — full reload purges its rules.
    loader._load_rows([], LoadReport(loader="rate_rule"))
    assert RateBand.objects.count() == 0


@pytest.mark.django_db
def test_load_rows_expands_occupancy_bands_with_gap_fallback(loaded_plan: RatePlan) -> None:
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
    loader = RateBandLoader()
    report = LoadReport(loader="rate_rule")
    loader._load_rows(rows, report)

    assert report.errors == []
    rules = {r.legacy_id: r for r in RateBand.objects.all()}
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
    # The four occupancy bands share one period (same Jun1-14 dates); the simple
    # rate gets its own period.
    assert RatePeriod.objects.filter(plan=loaded_plan).count() == 2

    # Full-replace idempotency: a second run reproduces the identical row set.
    second = LoadReport(loader="rate_rule")
    loader._load_rows(rows, second)
    assert second.errors == []
    assert RateBand.objects.count() == 5


@pytest.mark.django_db
def test_load_rows_flags_occupancy_plan(loaded_plan: RatePlan) -> None:
    """A banded (IsOccupationPrice) season ends up with >1 party bracket, so the
    loader flags its RatePlan `prices_by_occupancy`."""
    rows = [
        _row(
            ID=1,
            IsOccupationPrice=True,
            OccId=101,
            OccupencyFrom=2,
            OccupencyTo=4,
            OccupencyPrice=Decimal("500"),
        ),
        _row(
            ID=1,
            IsOccupationPrice=True,
            OccId=102,
            OccupencyFrom=5,
            OccupencyTo=6,
            OccupencyPrice=Decimal("700"),
        ),
    ]
    RateBandLoader()._load_rows(rows, LoadReport(loader="rate_rule"))
    loaded_plan.refresh_from_db()
    assert loaded_plan.prices_by_occupancy is True


@pytest.mark.django_db
def test_load_rows_leaves_flat_plan_unflagged(loaded_plan: RatePlan) -> None:
    """A season with a single full-span band stays flat (not by occupancy)."""
    RateBandLoader()._load_rows([_row(ID=1)], LoadReport(loader="rate_rule"))
    loaded_plan.refresh_from_db()
    assert loaded_plan.prices_by_occupancy is False


@pytest.mark.django_db
def test_load_rows_null_bound_band_does_not_abort_load(loaded_plan: RatePlan) -> None:
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
    loader = RateBandLoader()
    report = LoadReport(loader="rate_rule")
    loader._load_rows(rows, report)

    assert report.errors == []
    rules = {r.legacy_id: r for r in RateBand.objects.all()}
    assert set(rules) == {"occ-101", "occ-fb-1-0", "occ-fb-1-1"}
    # Dropped band (5,6)'s range is folded into the above gap fallback (5-8).
    assert (rules["occ-fb-1-1"].min_party, rules["occ-fb-1-1"].max_party) == (5, 8)


@pytest.mark.django_db
def test_load_rows_creates_disjoint_periods_for_overlapping_party_rows(
    loaded_plan: RatePlan,
) -> None:
    """Two party-disjoint but date-overlapping legacy rows both survive the
    resolver (no party conflict). Naively stamping each with its own date span
    would give overlapping periods ([Jun1-Jun20] and [Jun1-Jun10]). The loader
    must instead segment the plan onto a disjoint date axis (fragmenting the
    wider rule) — the invariant Unit 9's periods-disjoint EXCLUDE enforces."""
    rows = [
        _row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 20), PartySize=2),
        _row(ID=2, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 10), PartySize=5),
    ]
    loader = RateBandLoader()
    loader._load_rows(rows, LoadReport(loader="rate_rule"))

    periods = list(RatePeriod.objects.filter(plan=loaded_plan).order_by("date_from", "date_to"))
    spans = [(p.date_from, p.date_to) for p in periods]
    # Disjoint: no two periods overlap (inclusive dates).
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            assert not (spans[i][0] <= spans[j][1] and spans[j][0] <= spans[i][1]), spans
    # Every loaded rule hangs off a period (period FK is non-null by model).
    rules = RateBand.objects.filter(period__plan=loaded_plan)
    assert rules.exists()
    assert all(r.period_id is not None for r in rules)
    # The wider rule was fragmented across the segment boundary at Jun 10/11.
    assert spans == [(date(2025, 6, 1), date(2025, 6, 10)), (date(2025, 6, 11), date(2025, 6, 20))]
    # GAP-059: every synthesized period carries the derived date-span name
    # (legacy has no period-name column to draw from).
    assert [p.name for p in periods] == ["1\u201310 Jun", "11\u201320 Jun"]


@pytest.mark.django_db
def test_load_rows_mid_punch_keeps_both_sides(loaded_plan: RatePlan) -> None:
    """A winner strictly inside a loser's span splits the loser: BOTH remainders
    persist (BUG-016 canonical semantics — the old resolver clipped to the
    larger side), the later-date fragment namespaced `#seg1`."""
    rows = [
        _row(ID=1, FromDate=date(2025, 6, 10), ToDate=date(2025, 6, 12)),
        _row(ID=2, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 30)),
    ]
    RateBandLoader()._load_rows(rows, LoadReport(loader="rate_rule"))

    by_span = {
        (b.period.date_from, b.period.date_to): b.legacy_id
        for b in RateBand.objects.select_related("period")
    }
    assert by_span == {
        (date(2025, 6, 1), date(2025, 6, 9)): "2",
        (date(2025, 6, 10), date(2025, 6, 12)): "1",
        (date(2025, 6, 13), date(2025, 6, 30)): "2#seg1",
    }


@pytest.mark.django_db
def test_load_rows_single_day_remainder_persisted(loaded_plan: RatePlan) -> None:
    """A collision leaving a one-day remainder persists it as a single-day
    period (the old resolver's strict `<` remainder rule dropped it)."""
    rows = [
        _row(ID=1, FromDate=date(2025, 6, 2), ToDate=date(2025, 6, 10)),
        _row(ID=2, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 10)),
    ]
    RateBandLoader()._load_rows(rows, LoadReport(loader="rate_rule"))

    by_span = {
        (b.period.date_from, b.period.date_to): b.legacy_id
        for b in RateBand.objects.select_related("period")
    }
    assert by_span == {
        (date(2025, 6, 1), date(2025, 6, 1)): "2",
        (date(2025, 6, 2), date(2025, 6, 10)): "1",
    }


@pytest.mark.django_db
def test_load_rows_party_split_loser_keeps_all_brackets(loaded_plan: RatePlan) -> None:
    """Identical dates, winner (3,3), loser (1, capacity): the loser persists
    BOTH uncovered brackets (the old transform picked only the first surviving
    interval), bare legacy_id on the LOWEST bracket, `#seg1` on the upper."""
    rows = [
        _row(ID=1, PartySize=3),
        _row(ID=2, PartySize=None),
    ]
    RateBandLoader()._load_rows(rows, LoadReport(loader="rate_rule"))

    bands = {b.legacy_id: (b.min_party, b.max_party) for b in RateBand.objects.all()}
    assert bands == {"1": (3, 3), "2": (1, 2), "2#seg1": (4, 8)}
    # One shared date span — all three bands hang off a single period.
    assert RatePeriod.objects.filter(plan=loaded_plan).count() == 1


@pytest.mark.django_db
def test_load_rows_approved_later_row_beats_unapproved_earlier(loaded_plan: RatePlan) -> None:
    """Precedence is (not approved, id, disc): an approved higher-ID row wins
    the contested span over an unapproved lower-ID one."""
    rows = [
        _row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 10), IsApprove=False),
        _row(ID=2, FromDate=date(2025, 6, 5), ToDate=date(2025, 6, 20), IsApprove=True),
    ]
    RateBandLoader()._load_rows(rows, LoadReport(loader="rate_rule"))

    by_span = {
        (b.period.date_from, b.period.date_to): b.legacy_id
        for b in RateBand.objects.select_related("period")
    }
    assert by_span == {
        (date(2025, 6, 1), date(2025, 6, 4)): "1",
        (date(2025, 6, 5), date(2025, 6, 20)): "2",
    }


@pytest.mark.django_db
def test_load_rows_periods_stable_and_disjoint_across_reruns(loaded_plan: RatePlan) -> None:
    """Full-reload idempotency for the period axis: a second load of the same
    rows reproduces the identical disjoint period set with no stale-period
    accumulation (the purge must not leave orphans behind)."""

    def rows() -> list[dict[str, object]]:
        return [
            _row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 20), PartySize=2),
            _row(ID=2, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 10), PartySize=5),
        ]

    loader = RateBandLoader()
    loader._load_rows(rows(), LoadReport(loader="rate_rule"))
    first_spans = sorted(RatePeriod.objects.values_list("date_from", "date_to", "name"))
    first_period_count = RatePeriod.objects.count()

    loader._load_rows(rows(), LoadReport(loader="rate_rule"))
    second_spans = sorted(RatePeriod.objects.values_list("date_from", "date_to", "name"))

    assert second_spans == first_spans  # stable — no drift
    assert RatePeriod.objects.count() == first_period_count  # no stale accumulation
    assert all(r.period_id is not None for r in RateBand.objects.all())


@pytest.mark.django_db
def test_load_rows_purge_spares_ui_rules(loaded_plan: RatePlan) -> None:
    """The purge is scoped to legacy_id-bearing rules/periods; UI-created rows
    (legacy_id NULL) survive a full reload untouched."""
    ui_period = RatePeriod.objects.create(
        plan=loaded_plan,
        name="UI January",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
    )
    ui_rule = RateBand.objects.create(
        period=ui_period,
        min_party=1,
        max_party=8,
        weekly=Decimal("900"),
    )
    loader = RateBandLoader()
    loader._load_rows(
        [_row(ID=1, FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 8))],
        LoadReport(loader="rate_rule"),
    )
    assert RateBand.objects.filter(pk=ui_rule.pk).exists()
    assert RatePeriod.objects.filter(pk=ui_period.pk).exists()
