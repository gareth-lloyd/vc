"""Shared fixtures for the seed_dev test suite.

`seed_dev`'s `properties` stage looks up canonical ISO-3166 `Country` rows by
iso2 (seeded by data migration `0009_seed_iso_3166_countries`) and fails loudly
if one is missing. Under `--reuse-db`, the first `transaction=True` test flushes
every table on teardown — including those migration-seeded countries — and they
are never re-seeded. After that, every later test in the session (transactional
*or* not) sees an empty committed country table and the seeder crashes.

The autouse fixture below idempotently ensures the countries exist before each
seed_dev test that touches the DB: re-seeded after the flush for transactional
tests, and seeded inside the rolled-back transaction for non-transactional ones
(equivalent to the migration rows they used to rely on).
"""

from __future__ import annotations

from typing import Any

import pytest


def _ensure_iso_countries() -> None:
    from django_countries import countries as dc_countries

    from properties.models import Country

    if Country.objects.exists():
        return
    Country.objects.bulk_create(
        [
            Country(
                iso2=iso2,
                name=str(name),
                iso3=dc_countries.alpha3(iso2) or iso2 + "_",
                sort_order=sort_order,
                is_active=True,
            )
            for sort_order, (iso2, name) in enumerate(dc_countries)
        ],
        ignore_conflicts=True,
    )


@pytest.fixture(autouse=True)
def _ensure_countries_for_seed_dev(request: Any) -> None:
    """Ensure ISO countries exist for every seed_dev test that uses the DB.

    Picks the DB fixture matching the test's mode so transactional tests get
    their flushed countries restored, while non-transactional tests seed within
    their own rolled-back transaction. Tests with no `django_db` marker (e.g.
    the guardrail test) are skipped.
    """
    marker = request.node.get_closest_marker("django_db")
    if marker is None:
        return
    is_transactional = bool(marker.kwargs.get("transaction") or (marker.args and marker.args[0]))
    request.getfixturevalue("transactional_db" if is_transactional else "db")
    _ensure_iso_countries()
