"""Data guard for migration 0026 (geo-region-pickers).

The pre-idempotency `RegionFactory` minted a fresh Region per seed call, so a
dev DB holds every locality 3-4x (`region-<token>-<n>` slugs, `legacy_id`
NULL). 0026 collapses each `(country, name)` group to one canonical row —
preferring a legacy-loaded row, else the lowest id — repoints the only two
Region FKs (`Property.region`, `Enquiry.region`), deletes only the
`legacy_id IS NULL` losers, then re-slugs kept factory rows to
`slugify(name)` where collision-free.

Drives the real migration with `MigrationExecutor`: rolls back to 0025 (a
noop — 0026 is data-only), seeds the dirty shapes, rolls forward and asserts
the collapse. Legacy rows must never be deleted: legacy name collisions per
country are real (the loader suffixes slugs with the legacy id for exactly
that reason)."""

from __future__ import annotations

from typing import cast

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from properties.models import Country, Property, Region
from reservations.factories import EnquiryFactory
from reservations.models import Enquiry

_APP = "properties"
_BEFORE = "0025_alter_propertysettings_min_nights_rental_note"
_AFTER = "0026_dedupe_factory_regions"


def _migrate(target: str) -> None:
    executor = MigrationExecutor(connection)
    executor.migrate([(_APP, target)])
    executor.loader.build_graph()


def _region(country: Country, name: str, slug: str, legacy_id: str | None = None) -> Region:
    # Bypass the (now idempotent) factory — the whole point is to recreate the
    # duplicated rows the old factory produced.
    return Region.objects.create(country=country, name=name, slug=slug, legacy_id=legacy_id)


@pytest.mark.django_db(transaction=True)
def test_migration_0026_collapses_factory_dupes_and_repoints_fks() -> None:
    pt = Country.objects.get(iso2="PT")
    es = Country.objects.get(iso2="ES")

    # The two FK-holders (a Property + an Enquiry) are created at the migration
    # LEAF, before any rollback: the real models carry columns the rolled-back
    # 0026 schema lacks (e.g. Property.video_url, added in 0033), so creating
    # them mid-rollback would INSERT a column that doesn't exist yet. Rolling
    # back drops those columns but keeps the rows; below we only UPDATE their
    # region FK and read it back column-scoped (mirrors the 0017/0027 tests).
    prop = cast(Property, EnquiryFactory().property)
    enquiry = cast(Enquiry, EnquiryFactory())

    try:
        _migrate(_BEFORE)

        # Case 1 — three factory dupes; properties + an enquiry point at losers.
        keep = _region(pt, "Algarve", "region-aaaa-1")
        lose_a = _region(pt, "Algarve", "region-aaaa-21")
        lose_b = _region(pt, "Algarve", "region-aaaa-41")
        Property.objects.filter(pk=prop.pk).update(region=lose_a)
        Enquiry.objects.filter(pk=enquiry.pk).update(region=lose_b)

        # Case 2 — factory row merges INTO the legacy row despite a higher id.
        factory_row = _region(es, "Ibiza", "region-bbbb-3")
        legacy_row = _region(es, "Ibiza", "ibiza-1042", legacy_id="1042")

        # Case 3 — two legacy rows with the same name both survive.
        legacy_dupe_a = _region(es, "Mallorca", "mallorca-2001", legacy_id="2001")
        legacy_dupe_b = _region(es, "Mallorca", "mallorca-2002", legacy_id="2002")

        # Case 4 — a factory region named "Unknown" folds into the sentinel.
        sentinel = _region(pt, "Unknown", "unknown-pt", legacy_id="__unknown__")
        factory_unknown = _region(pt, "Unknown", "region-cccc-7")

        # Case 5 — re-slug collision: slugify(name) already owned by another
        # region in the same country -> the factory slug is kept.
        _region(pt, "Douro", "douro")
        blocked = _region(pt, "DOURO", "region-dddd-9")  # different name, same slugify

        _migrate(_AFTER)

        # Case 1: one Algarve left, canonical = lowest id, FKs repointed,
        # kept factory slug rewritten to slugify(name).
        algarve = Region.objects.get(country=pt, name="Algarve")
        assert algarve.pk == keep.pk
        assert algarve.slug == "algarve"
        assert not Region.objects.filter(pk__in=[lose_a.pk, lose_b.pk]).exists()
        # Column-scoped: at state 0026 the real Property model's `video_url`
        # (0033) column isn't in the schema, so a full-row fetch would fail.
        assert Property.objects.filter(pk=prop.pk).values_list("region_id", flat=True).first() == (
            keep.pk
        )
        assert Enquiry.objects.get(pk=enquiry.pk).region_id == keep.pk

        # Case 2: legacy row canonical, factory row gone, legacy slug untouched.
        ibiza = Region.objects.get(country=es, name="Ibiza")
        assert ibiza.pk == legacy_row.pk
        assert ibiza.slug == "ibiza-1042"
        assert not Region.objects.filter(pk=factory_row.pk).exists()

        # Case 3: legacy rows are never deleted, even as same-name "dupes".
        assert Region.objects.filter(pk__in=[legacy_dupe_a.pk, legacy_dupe_b.pk]).count() == 2

        # Case 4: sentinel canonical, factory "Unknown" gone.
        assert Region.objects.get(country=pt, name="Unknown").pk == sentinel.pk
        assert not Region.objects.filter(pk=factory_unknown.pk).exists()

        # Case 5: colliding re-slug is skipped, factory slug kept.
        assert Region.objects.get(pk=blocked.pk).slug == "region-dddd-9"
    finally:
        # Restore the whole project to its migration leaves (see the 0017 test
        # for why restoring only this app poisons the shared xdist DB).
        call_command("migrate", verbosity=0)
