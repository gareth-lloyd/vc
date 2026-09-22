"""Data-level tests for `properties.0010_description_block_set`.

Same posture as `test_migration_0007`: there is no migration-executor helper
in this suite, so the `RunPython` callables run directly against the live app
registry. Unlike 0007 there is **no widen** — `section` has been
`max_length=32` since 0005 and the longest new value (`interior_para`) is 13
chars. What the `AlterField` carries is the new `choices` list, and the real
`makemigrations --check` failure mode is a choices list that has drifted out
of enum order, so that is what gets pinned here.
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps
from django.db import migrations

from properties.enums import DescriptionSection
from properties.models import Property, PropertyDescription

migration = importlib.import_module("properties.migrations.0010_description_block_set")


def _seed(property_: Property, section: str, body: str | None = None) -> None:
    # Django never validates `choices` on save, so retired values store fine.
    PropertyDescription.objects.create(
        property=property_,
        section=section,
        body=body if body is not None else f"{section} body",
        legacy_id=f"42-{section}",
    )


def _sections(property_: Property) -> dict[str, PropertyDescription]:
    return {d.section: d for d in PropertyDescription.objects.filter(property=property_)}


def test_alterfield_then_runpython_with_choices_in_enum_order() -> None:
    ops = migration.Migration.operations
    assert [type(op) for op in ops] == [migrations.AlterField, migrations.RunPython]
    # 0010's list is the enum as it stood then; 0011 retired `overview`, so
    # the live enum is this list minus that one entry, order intact.
    assert [c for c in migration.SECTION_CHOICES if c[0] != "overview"] == (
        DescriptionSection.choices
    )
    assert ops[0].field.max_length == 32


@pytest.mark.django_db
def test_forwards_remaps_the_retired_website_sections(property_: Property) -> None:
    _seed(property_, "web_description")
    _seed(property_, "location")
    _seed(property_, "house_rules")

    migration._forwards(apps, None)

    rows = _sections(property_)
    assert set(rows) == {"web_des_1", "location_sub", "house_rules"}
    # The fused body lands in the *sub* slot: the loader joined part 1 first.
    assert rows["web_des_1"].body == "web_description body"
    assert rows["web_des_1"].legacy_id == "42-web_description"
    assert rows["location_sub"].body == "location body"


@pytest.mark.django_db
def test_forwards_moves_further_info_into_internal_notes(property_: Property) -> None:
    _seed(property_, "further_info")

    migration._forwards(apps, None)

    rows = _sections(property_)
    assert set(rows) == {"internal_notes"}
    assert rows["internal_notes"].body == "further_info body"


@pytest.mark.django_db
def test_forwards_appends_further_info_when_internal_notes_exists(property_: Property) -> None:
    _seed(property_, "internal_notes", body="Staff wrote this")
    _seed(property_, "further_info", body="Legacy Notes")

    migration._forwards(apps, None)

    rows = _sections(property_)
    assert set(rows) == {"internal_notes"}
    assert rows["internal_notes"].body == "Staff wrote this\n\nLegacy Notes"
    # The surviving row is the staff one, provenance intact.
    assert rows["internal_notes"].legacy_id == "42-internal_notes"


@pytest.mark.django_db
def test_forwards_handles_colliding_and_free_properties_together(property_: Property) -> None:
    other = Property.objects.create(
        name="Other Villa",
        display_name="Other Villa",
        slug="other-villa",
        region=property_.region,
    )
    _seed(property_, "internal_notes", body="Staff")
    _seed(property_, "further_info", body="Legacy")
    _seed(other, "further_info", body="Only legacy")

    migration._forwards(apps, None)

    assert _sections(property_)["internal_notes"].body == "Staff\n\nLegacy"
    assert _sections(other)["internal_notes"].body == "Only legacy"
    assert not PropertyDescription.objects.filter(section="further_info").exists()


@pytest.mark.django_db
def test_backwards_restores_the_website_sections_but_not_internal_notes(
    property_: Property,
) -> None:
    _seed(property_, "web_des_1")
    _seed(property_, "location_sub")
    _seed(property_, "internal_notes")
    _seed(property_, "interior_para")

    migration._backwards(apps, None)

    rows = _sections(property_)
    # `interior_para` and a remapped `internal_notes` are indistinguishable
    # from genuine rows, so reversing them would corrupt real copy (the 0007
    # precedent with `rooms`).
    assert set(rows) == {"web_description", "location", "internal_notes", "interior_para"}
