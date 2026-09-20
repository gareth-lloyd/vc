# GAP-090: the website description set becomes the legacy sub/para block set.
#
# `section` needs no widen — it has been `max_length=32` since 0005 and the
# longest new value (`interior_para`) is 13 chars — so the `AlterField` here
# carries only the new `choices` list. Three retired values are remapped:
#
#   web_description -> web_des_1     (fused WebDesc1+WebDesc2 body)
#   location        -> location_sub  (fused Location1+Location2 body)
#   further_info    -> internal_notes
#
# The two website bodies land in the *sub* slot because the loader joined
# part 1 first; no string split can undo the fusing, so they stay fused until
# the `loadlegacy property` re-run documented in `data_migration/CUTOVER.md`
# §6i rewrites each half into its own section.
#
# `further_info` and `internal_notes` are both staff-only copy, so where a
# property holds both the two bodies are concatenated onto the existing
# `internal_notes` row and the source row is deleted —
# `one_description_per_section` is unique, so a blanket `.update()` would
# raise. Everything else moves by bulk `.update()`, which bypasses AuditLog on
# purpose (a schema rename, not a user edit; sanctioned for `RunPython` in
# django_res/CLAUDE.md §AuditLog). `core.audit.track` connects its receivers
# with `sender=<concrete model>`, so the historical model here fires none
# either: the deleted source row leaves no tombstone and the migration
# itself is the trail. (`test_migration_0010` runs the callables against the
# live registry for convenience, so it cannot observe that — the tombstone
# it would write is an artefact of the test harness, not of a real run.)

from __future__ import annotations

from typing import Any

from django.db import migrations, models

SECTION_CHOICES = [
    ("overview", "Overview"),
    ("house_rules", "House rules"),
    ("web_des_1", "Web des 1"),
    ("web_des_2", "Web des 2"),
    ("interior_sub", "Interior sub"),
    ("interior_para", "Interior para"),
    ("exterior_sub", "Exterior sub"),
    ("exterior_para", "Exterior para"),
    ("location_sub", "Location sub"),
    ("location_para", "Location para"),
    ("internal_notes", "Internal notes"),
    ("other_information", "Other information"),
    ("rooms", "Rooms"),
]


def _forwards(apps: Any, schema_editor: Any) -> None:
    PropertyDescription = apps.get_model("properties", "PropertyDescription")

    PropertyDescription.objects.filter(section="web_description").update(section="web_des_1")
    PropertyDescription.objects.filter(section="location").update(section="location_sub")

    # Properties holding both: merge, then move the rest in bulk.
    notes_by_property = {
        row.property_id: row for row in PropertyDescription.objects.filter(section="internal_notes")
    }
    colliding: list[int] = []
    for source in PropertyDescription.objects.filter(
        section="further_info", property_id__in=notes_by_property
    ):
        target = notes_by_property[source.property_id]
        target.body = "\n\n".join(p for p in (target.body, source.body) if p)
        target.save(update_fields=["body", "updated_at"])
        source.delete()
        colliding.append(source.property_id)

    PropertyDescription.objects.filter(section="further_info").exclude(
        property_id__in=colliding
    ).update(section="internal_notes")


def _backwards(apps: Any, schema_editor: Any) -> None:
    # Only the two website renames reverse. A remapped `internal_notes` row is
    # indistinguishable from a genuine staff-written one, and the new
    # interior/exterior/`_2`/`_para` rows have no pre-0010 home, so both are
    # left in place — the 0007 precedent with `rooms`. Pre-0010 code 404s
    # those slugs until the migration is re-applied.
    PropertyDescription = apps.get_model("properties", "PropertyDescription")
    PropertyDescription.objects.filter(section="web_des_1").update(section="web_description")
    PropertyDescription.objects.filter(section="location_sub").update(section="location")


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0009_propertyfinance_legacy_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="propertydescription",
            name="section",
            field=models.CharField(choices=SECTION_CHOICES, max_length=32),
        ),
        migrations.RunPython(_forwards, _backwards),
    ]
