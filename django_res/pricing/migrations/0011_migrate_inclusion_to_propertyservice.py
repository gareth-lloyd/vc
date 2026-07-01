"""GAP-037: backfill the free-text RatePlan.inclusion into PropertyService.

Each plan with a non-empty `inclusion` gets one date-banded PropertyService on
its property (sharing the plan's effective dates). Keyed `<plan.legacy_id>:svc`
so the legacy loader's own upsert (RatePlanLoader._process_row) converges on the
same row; UI-created plans (no legacy_id) are deduped on property + copy + band.
Idempotent. The `inclusion` column itself is dropped in 0012, once every reader
is repointed (Unit 3).
"""

from __future__ import annotations

from typing import Any

from django.db import migrations


def migrate_inclusions_to_services(apps: Any, schema_editor: Any) -> None:
    RatePlan = apps.get_model("pricing", "RatePlan")
    PropertyService = apps.get_model("properties", "PropertyService")

    plans = RatePlan.objects.exclude(inclusion="").exclude(inclusion__isnull=True)
    for plan in plans.iterator():
        legacy = f"{plan.legacy_id}:svc" if plan.legacy_id else None
        if legacy:
            if PropertyService.objects.filter(legacy_id=legacy).exists():
                continue
        elif PropertyService.objects.filter(
            property_id=plan.property_id,
            copy=plan.inclusion,
            applies_from=plan.effective_from,
            applies_to=plan.effective_to,
        ).exists():
            continue
        PropertyService.objects.create(
            property_id=plan.property_id,
            name="Included services",
            copy=plan.inclusion,
            applies_from=plan.effective_from,
            applies_to=plan.effective_to,
            is_active=plan.is_active,
            legacy_id=legacy,
        )


def remove_backfilled_services(apps: Any, schema_editor: Any) -> None:
    # Reverse: drop the cutover-keyed rows this backfill created. UI-origin rows
    # (null legacy_id) are left in place — a forward re-run dedupes them anyway.
    PropertyService = apps.get_model("properties", "PropertyService")
    PropertyService.objects.filter(legacy_id__endswith=":svc").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0010_remove_raterule_priority"),
        ("properties", "0022_propertyservice"),
    ]

    operations = [
        migrations.RunPython(migrate_inclusions_to_services, remove_backfilled_services),
    ]
