"""Backfill lucide icon names onto the feature catalogue by slug.

Idempotent and additive: only fills `icon` where it is currently blank, so an
operator's manual choice (or a re-run) is never clobbered. The slug->icon map is
inlined here on purpose — migrations must not depend on mutable app code; the
dev seeder (`seeding/stages/features.py`) keeps its own copy of the same data.
"""

from __future__ import annotations

from django.db import migrations

_CATEGORY_ICONS = {
    "outdoor": "trees",
    "kitchen": "utensils-crossed",
    "bedroom": "bed-double",
    "bathroom": "bath",
    "entertainment": "tv",
}

_FEATURE_ICONS = {
    "pool": "waves",
    "hot-tub": "droplets",
    "bbq": "flame",
    "garden": "sprout",
    "sea-view": "sailboat",
    "dishwasher": "utensils",
    "oven": "cooking-pot",
    "coffee-machine": "coffee",
    "welcome-pack": "gift",
    "private-chef": "chef-hat",
    "king-bed": "bed-double",
    "cot": "baby",
    "blackout": "blinds",
    "ensuite-bathroom": "shower-head",
    "rain-shower": "droplets",
    "bath-tub": "bath",
    "smart-tv": "tv",
    "wifi": "wifi",
    "games-room": "gamepad-2",
    "daily-housekeeping": "sparkles",
}


def forwards(apps, schema_editor):
    FeatureCategory = apps.get_model("properties", "FeatureCategory")
    Feature = apps.get_model("properties", "Feature")
    for model, mapping in ((FeatureCategory, _CATEGORY_ICONS), (Feature, _FEATURE_ICONS)):
        for slug, icon in mapping.items():
            model.objects.filter(slug=slug, icon="").update(icon=icon)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0011_hold_duration_hours"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
