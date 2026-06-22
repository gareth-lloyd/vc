"""GAP-046 Unit 5b — drop the free-text ``Person.company`` (expand→contract).

Before the column is removed, fold every non-blank ``company`` string into a
deduplicated ``Organisation(org_type="agency")`` and link ``Person.agency`` — the
existing-DB counterpart of the loader reroute (Unit 4) that already writes
``agency`` on a fresh rebuild. The data step runs FIRST, then ``RemoveField``.
"""

from __future__ import annotations

import hashlib
from typing import Any

from django.db import migrations


def _frozen_company_dedup_key(name: str) -> str:
    """FROZEN copy of ``accounts.services.organisations.company_dedup_key``.

    A data migration must not import live app code (that would couple the
    historical migration to a module that can change shape under it), so the
    dedup-key algorithm is inlined here verbatim. ``test_migration_0012_…`` pins
    this against the live ``company_dedup_key`` so the two can never drift —
    change one, change both, or the migration mints duplicate orgs.
    """
    norm = " ".join(name.split()).casefold()
    digest = hashlib.sha1(norm.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"org-{digest[:24]}"


def _backfill_agency_from_company(apps: Any, schema_editor: Any) -> None:
    """Link each company-bearing Person to a deduped agency Organisation.

    Idempotent and collision-safe: case/whitespace variants share one
    ``dedup_key`` (unique since 0010) so they converge on a single row; the
    ``agency__isnull=True`` filter means a re-run touches nothing and an already
    -linked Person is never clobbered. Mirrors the live chokepoint
    ``organisation_for_company_name`` (raw name → key, stripped name → display).
    """
    Person = apps.get_model("accounts", "Person")
    Organisation = apps.get_model("accounts", "Organisation")
    rows = Person.objects.filter(agency__isnull=True).exclude(company="").iterator()
    for person in rows:
        company = person.company or ""
        if not company.strip():
            continue
        org, _ = Organisation.objects.get_or_create(
            dedup_key=_frozen_company_dedup_key(company),
            defaults={"name": company.strip(), "org_type": "agency"},
        )
        person.agency_id = org.pk
        person.save(update_fields=["agency"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0011_person_agency"),
    ]

    operations = [
        # MUST precede RemoveField: it reads `company` via the historical model,
        # which still has the column until the next operation drops it.
        migrations.RunPython(_backfill_agency_from_company, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="person",
            name="company",
        ),
    ]
