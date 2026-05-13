"""Seed canonical ISO-3166 countries via django-countries.

Idempotent: `get_or_create` by iso2 so re-running leaves existing rows
(including legacy-imported countries that already have a legacy_id) alone.
"""

from __future__ import annotations

from django.db import migrations


def forwards(apps, schema_editor):
    Country = apps.get_model("properties", "Country")
    from django_countries import countries as dc_countries

    for sort_order, (iso2, name) in enumerate(dc_countries):
        iso3 = dc_countries.alpha3(iso2) or iso2 + "_"
        Country.objects.get_or_create(
            iso2=iso2,
            defaults={
                "name": str(name),
                "iso3": iso3,
                "sort_order": sort_order,
                "is_active": True,
            },
        )


def backwards(apps, schema_editor):
    # Non-destructive — leave seeded countries in place on reverse.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0008_propertycontactassignment_legacy_id"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
