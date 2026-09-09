"""Data-level tests for `properties.0007_description_other_information`.

There is no migration-executor helper in this suite, so the `RunPython`
callables are exercised directly against the live app registry: the schema
they need (`section` widened to 32) is already applied, and the functions
only touch `PropertyDescription.section`. The operation order is pinned
separately — the widen MUST precede the rename or Postgres rejects the
17-char value.
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps
from django.db import migrations

from properties.models import Property, PropertyDescription

migration = importlib.import_module("properties.migrations.0007_description_other_information")


def _seed(property_: Property, section: str, legacy_id: str | None = None) -> None:
    # Django never validates `choices` on save, so the retired value stores fine.
    PropertyDescription.objects.create(
        property=property_, section=section, body=f"{section} body", legacy_id=legacy_id
    )


def test_widen_runs_before_rename() -> None:
    ops = migration.Migration.operations
    assert [type(op) for op in ops] == [migrations.AlterField, migrations.RunPython]
    assert ops[0].field.max_length == 32


@pytest.mark.django_db
def test_forwards_renames_villa_info_rows_only(property_: Property) -> None:
    _seed(property_, "villa_info", legacy_id="42-villa_info")
    _seed(property_, "house_rules")

    migration._forwards(apps, None)

    rows = {d.section: d for d in PropertyDescription.objects.filter(property=property_)}
    assert set(rows) == {"other_information", "house_rules"}
    assert rows["other_information"].body == "villa_info body"
    assert rows["other_information"].legacy_id == "42-villa_info"
    assert rows["house_rules"].body == "house_rules body"


@pytest.mark.django_db
def test_backwards_restores_villa_info(property_: Property) -> None:
    _seed(property_, "other_information")
    _seed(property_, "rooms")

    migration._backwards(apps, None)

    sections = set(
        PropertyDescription.objects.filter(property=property_).values_list("section", flat=True)
    )
    assert sections == {"villa_info", "rooms"}
