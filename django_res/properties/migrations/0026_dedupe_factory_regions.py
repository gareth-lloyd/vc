"""Collapse duplicated factory-minted Regions (geo-region-pickers).

The pre-idempotency `RegionFactory` created a fresh Region per seed call
(`region-<token>-<n>` slugs, `legacy_id` NULL), so dev/staging DBs hold every
locality 3-4x. Each `(country, name)` group collapses to one canonical row:
a legacy-loaded row when present (lowest id tie-break), else the lowest id.
`Property.region` and `Enquiry.region` — the only two Region FKs — are
repointed before deletion; rows with a `legacy_id` (including the
`__unknown__` sentinels) are NEVER deleted, because legacy name collisions
per country are real. Kept factory rows finally trade their opaque
`region-*` slug for `slugify(name)` where that is collision-free.

Reverse is a noop: the deleted duplicates and their old FK targets are
genuinely unrecoverable, and no schema changes.
"""

from __future__ import annotations

from collections import defaultdict

from django.db import migrations
from django.utils.text import slugify


def dedupe_regions(apps, schema_editor):  # type: ignore[no-untyped-def]
    Region = apps.get_model("properties", "Region")
    Property = apps.get_model("properties", "Property")
    Enquiry = apps.get_model("reservations", "Enquiry")

    groups: dict[tuple[int, str], list] = defaultdict(list)
    for region in Region.objects.order_by("id"):
        groups[(region.country_id, region.name)].append(region)

    for rows in groups.values():
        if len(rows) < 2:
            continue
        legacy = [r for r in rows if r.legacy_id]
        canonical = legacy[0] if legacy else rows[0]
        loser_ids = [r.id for r in rows if r.id != canonical.id and not r.legacy_id]
        if not loser_ids:
            continue
        Property.objects.filter(region_id__in=loser_ids).update(region_id=canonical.id)
        Enquiry.objects.filter(region_id__in=loser_ids).update(region_id=canonical.id)
        Region.objects.filter(id__in=loser_ids).delete()

    # Surviving factory rows keep a human slug where it doesn't collide with
    # an existing slug in the same country (the (country, slug) constraint).
    for region in Region.objects.filter(legacy_id__isnull=True, slug__startswith="region-"):
        new_slug = slugify(region.name)
        if not new_slug or new_slug == region.slug:
            continue
        taken = (
            Region.objects.filter(country_id=region.country_id, slug=new_slug)
            .exclude(id=region.id)
            .exists()
        )
        if not taken:
            region.slug = new_slug
            region.save(update_fields=["slug"])


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0025_alter_propertysettings_min_nights_rental_note"),
        ("reservations", "0038_remove_damageclaim_photos_damageclaimphoto"),
    ]

    operations = [
        migrations.RunPython(dedupe_regions, migrations.RunPython.noop),
    ]
