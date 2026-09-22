"""Data-level tests for `properties.0011_retire_overview_section`.

Same posture as `test_migration_0010`: no migration-executor helper, so the
`RunPython` callable runs directly against the live app registry. What is
pinned: the operation order, the choices list being 0010's minus `overview`,
and that the forward pass deletes `overview` rows and nothing else, logging
each one.
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps
from django.db import migrations

from properties.models import Property, PropertyDescription

migration = importlib.import_module("properties.migrations.0011_retire_overview_section")
previous = importlib.import_module("properties.migrations.0010_description_block_set")


def _seed(property_: Property, section: str) -> None:
    # Django never validates `choices` on save, so the retired value stores fine.
    PropertyDescription.objects.create(
        property=property_, section=section, body=f"{section} body", legacy_id=f"42-{section}"
    )


def test_alterfield_then_runpython_dropping_only_overview() -> None:
    ops = migration.Migration.operations
    assert [type(op) for op in ops] == [migrations.AlterField, migrations.RunPython]
    # Pinned against 0010's list, not the live enum: that this is "0010 minus
    # `overview`" never changes, whereas the live enum will move again and
    # `makemigrations --check` is what guards choices drift.
    assert ops[0].field.choices == [c for c in previous.SECTION_CHOICES if c[0] != "overview"]
    assert ops[0].field.max_length == 32
    assert ops[1].reverse_code is migrations.RunPython.noop


@pytest.mark.django_db
def test_forwards_deletes_overview_rows_only(property_: Property) -> None:
    other = Property.objects.create(
        name="Other Villa", display_name="Other Villa", slug="other-villa", region=property_.region
    )
    _seed(property_, "overview")
    _seed(property_, "web_des_1")
    _seed(property_, "house_rules")
    _seed(other, "overview")

    migration._forwards(apps, None)

    assert not PropertyDescription.objects.filter(section="overview").exists()
    assert set(
        PropertyDescription.objects.filter(property=property_).values_list("section", flat=True)
    ) == {"web_des_1", "house_rules"}
    # Never remapped: the retired copy does not become the website's top text.
    assert not PropertyDescription.objects.filter(property=other).exists()
