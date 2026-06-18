"""Data-preservation guard for migration 0017 (GAP-022).

Switching `Property.features` from a plain auto-M2M to the `PropertyFeature`
through model must NOT drop a single existing link. The danger is that a naive
`makemigrations` would DROP the join table and CREATE an empty one; 0017 instead
reuses the table via `SeparateDatabaseAndState` with empty `database_operations`,
so the swap touches no rows and only the later `AddField` does real DDL.

This test drives the migration's actual DDL with `MigrationExecutor`: it seeds a
link at the current (post-0017) state, rolls back to 0016 (which drops the
`sort_order` column — the one reverse DDL), asserts the link survived the column
drop, then rolls forward to 0017 and asserts the link still survives, the pair is
intact, and the `sort_order` column physically exists again.
"""

from __future__ import annotations

from typing import cast

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from properties.factories import FeatureFactory, PropertyFactory
from properties.models import Feature, Property, PropertyFeature

_APP = "properties"
_BEFORE = "0016_alter_property_options"
_AFTER = "0017_propertyfeature_through"
_TABLE = "properties_property_features"


def _columns() -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            [_TABLE],
        )
        return {row[0] for row in cursor.fetchall()}


def _pairs() -> set[tuple[int, int]]:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT property_id, feature_id FROM {_TABLE}")
        return set(cursor.fetchall())


def _migrate(target: str) -> None:
    executor = MigrationExecutor(connection)
    executor.migrate([(_APP, target)])
    # Drop the executor's cached project state so a later call re-reads the
    # schema it just changed.
    executor.loader.build_graph()


@pytest.mark.django_db(transaction=True)
def test_migration_0017_preserves_links_and_adds_sort_order() -> None:
    prop = cast(Property, PropertyFactory())
    feature = cast(Feature, FeatureFactory())
    PropertyFeature.objects.create(property=prop, feature=feature, sort_order=7)
    pair = (prop.pk, feature.pk)

    assert pair in _pairs()
    assert "sort_order" in _columns()

    try:
        # Roll back across 0017. The only reverse DDL is dropping `sort_order`;
        # the table and its rows must remain (the link is not a casualty).
        _migrate(_BEFORE)
        assert "sort_order" not in _columns(), "0016 should not have the column yet"
        assert pair in _pairs(), "rolling back 0017 must not drop the link row"

        # Roll forward again: link still there, pair intact, column re-created.
        _migrate(_AFTER)
        assert pair in _pairs(), "re-applying 0017 must preserve every link"
        assert _pairs() == {pair}, "no rows invented or lost"
        assert "sort_order" in _columns(), "0017 must physically add sort_order"
    finally:
        # Leave the DB fully migrated for the rest of the suite regardless of
        # where an assertion failed mid-round-trip.
        _migrate(_AFTER)
