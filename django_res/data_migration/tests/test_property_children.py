from __future__ import annotations

from typing import cast

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.property_children import PropertyFeatureMappingLoader
from properties.factories import FeatureFactory, PropertyFactory
from properties.models.features import Feature
from properties.models.property import Property


def _row(*, FeatureId: object, VillaId: object, MappingOrder: object) -> dict[str, object]:
    return {"FeatureId": FeatureId, "VillaId": VillaId, "MappingOrder": MappingOrder}


@pytest.mark.django_db
def test_load_rows_persists_sort_order_from_mapping_order() -> None:
    prop = cast(Property, PropertyFactory(legacy_id="500"))
    feature = cast(Feature, FeatureFactory(legacy_id="42"))

    loader = PropertyFeatureMappingLoader()
    report = LoadReport(loader="property_feature")
    loader._load_rows([_row(FeatureId="42", VillaId="500", MappingOrder=3)], report)

    assert (report.created, report.updated, report.skipped) == (1, 0, 0)
    through = Property.features.through
    link = through.objects.get(property_id=prop.pk, feature_id=feature.pk)
    assert link.sort_order == 3


@pytest.mark.django_db
def test_load_rows_mapping_order_zero_is_kept() -> None:
    """A legitimate MappingOrder of 0 must persist as 0 (no falsy-zero bug)."""
    prop = cast(Property, PropertyFactory(legacy_id="500"))
    feature = cast(Feature, FeatureFactory(legacy_id="42"))

    loader = PropertyFeatureMappingLoader()
    loader._load_rows(
        [_row(FeatureId="42", VillaId="500", MappingOrder=0)],
        LoadReport(loader="property_feature"),
    )

    through = Property.features.through
    assert through.objects.get(property_id=prop.pk, feature_id=feature.pk).sort_order == 0


@pytest.mark.django_db
def test_load_rows_rerun_updates_sort_order_and_reports_updated() -> None:
    prop = cast(Property, PropertyFactory(legacy_id="500"))
    feature = cast(Feature, FeatureFactory(legacy_id="42"))
    through = Property.features.through
    loader = PropertyFeatureMappingLoader()

    first = LoadReport(loader="property_feature")
    loader._load_rows([_row(FeatureId="42", VillaId="500", MappingOrder=1)], first)
    assert (first.created, first.updated) == (1, 0)

    second = LoadReport(loader="property_feature")
    loader._load_rows([_row(FeatureId="42", VillaId="500", MappingOrder=5)], second)
    assert (second.created, second.updated) == (0, 1)
    assert through.objects.get(property_id=prop.pk, feature_id=feature.pk).sort_order == 5
    assert through.objects.filter(property_id=prop.pk, feature_id=feature.pk).count() == 1


@pytest.mark.django_db
def test_load_rows_duplicate_pair_collapses_to_one_row() -> None:
    """The `update_or_create` backstop: if the in-SQL MIN dedup ever lets a
    duplicate pair through, the second row updates the first instead of
    violating the unique constraint."""
    prop = cast(Property, PropertyFactory(legacy_id="500"))
    feature = cast(Feature, FeatureFactory(legacy_id="42"))
    through = Property.features.through
    loader = PropertyFeatureMappingLoader()
    report = LoadReport(loader="property_feature")

    loader._load_rows(
        [
            _row(FeatureId="42", VillaId="500", MappingOrder=2),
            _row(FeatureId="42", VillaId="500", MappingOrder=7),
        ],
        report,
    )

    assert report.errors == []
    links = through.objects.filter(property_id=prop.pk, feature_id=feature.pk)
    assert links.count() == 1
    assert links.get().sort_order == 7


@pytest.mark.django_db
def test_load_rows_missing_legacy_id_is_skipped() -> None:
    PropertyFactory(legacy_id="500")  # feature deliberately absent
    loader = PropertyFeatureMappingLoader()
    report = LoadReport(loader="property_feature")

    loader._load_rows([_row(FeatureId="999", VillaId="500", MappingOrder=1)], report)

    assert (report.created, report.updated, report.skipped) == (0, 0, 1)
    assert Property.features.through.objects.count() == 0
