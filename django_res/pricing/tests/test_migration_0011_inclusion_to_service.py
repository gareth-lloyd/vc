"""Backfill guard for pricing migration 0011 (GAP-037).

The data migration copies each RatePlan's free-text `inclusion` into a
date-banded PropertyService, keyed `<plan.legacy_id>:svc` so a later
`loadlegacy` re-run upserts the same row; UI-created plans (no legacy_id) dedupe
on property + copy + band.

Driven through `MigrationExecutor` against the *historical* state so the guard
stays valid after 0012 drops the `inclusion` column: we seed RatePlan rows at the
pre-0011 state (where the column still exists), migrate forward across 0011, and
assert the services appear. The `finally` restores the whole project to its
leaves so the shared xdist worker DB is left at head.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.state import ProjectState

_BEFORE = [
    ("pricing", "0010_remove_raterule_priority"),
    ("properties", "0022_propertyservice"),
]
_AFTER = [("pricing", "0011_migrate_inclusion_to_propertyservice")]


def _migrate(targets: list[tuple[str, str]]) -> ProjectState:
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor.loader.project_state(targets)


def _seed_plan(apps_state: ProjectState, **plan_kwargs: object) -> None:
    Country = apps_state.apps.get_model("properties", "Country")
    Region = apps_state.apps.get_model("properties", "Region")
    PropertyCategory = apps_state.apps.get_model("properties", "PropertyCategory")
    PropertyGroup = apps_state.apps.get_model("properties", "PropertyGroup")
    Property = apps_state.apps.get_model("properties", "Property")
    Currency = apps_state.apps.get_model("pricing", "Currency")
    RatePlan = apps_state.apps.get_model("pricing", "RatePlan")

    country = Country.objects.get(iso2="GB")  # seeded by properties/0009
    region, _ = Region.objects.get_or_create(country=country, name="Cornwall", slug="cornwall")
    cat, _ = PropertyCategory.objects.get_or_create(name="Villa", slug="villa")
    group, _ = PropertyGroup.objects.get_or_create(name="G")
    slug = f"p-{plan_kwargs.get('legacy_id') or plan_kwargs['name']}"
    prop = Property.objects.create(
        name="P", display_name="P", slug=slug, category=cat, group=group, region=region
    )
    cur, _ = Currency.objects.get_or_create(code="EUR", defaults={"name": "Euro", "symbol": "€"})
    RatePlan.objects.create(property=prop, currency=cur, **plan_kwargs)


@pytest.mark.django_db(transaction=True)
def test_migration_0011_backfills_and_skips() -> None:
    before = _migrate(_BEFORE)
    try:
        _seed_plan(
            before,
            name="Summer",
            effective_from=date(2025, 6, 1),
            effective_to=date(2025, 8, 31),
            inclusion="Private chef included.",
            notes="Keep this note.",
            legacy_id="500",
        )
        _seed_plan(
            before,
            name="No inclusion",
            effective_from=date(2025, 1, 1),
            inclusion="",
            legacy_id="501",
        )

        after = _migrate(_AFTER)
        PropertyService = after.apps.get_model("properties", "PropertyService")
        RatePlan = after.apps.get_model("pricing", "RatePlan")

        svc = PropertyService.objects.get(legacy_id="500:svc")
        assert svc.copy == "Private chef included."
        assert svc.applies_from == date(2025, 6, 1)
        assert svc.applies_to == date(2025, 8, 31)
        assert svc.is_active is True
        # The plan keeps its operator notes; only inclusion moved.
        assert RatePlan.objects.get(legacy_id="500").notes == "Keep this note."
        # A blank inclusion produces no service.
        assert not PropertyService.objects.filter(legacy_id="501:svc").exists()
    finally:
        call_command("migrate", verbosity=0)
