"""Resolve a free-text company name to a deduplicated Organisation (GAP-046).

The single chokepoint the legacy loader and the company→agency backfill both
call: turn a raw `company` string into one canonical `Organisation(agency)`,
deduping case/whitespace variants onto a single row. Framework-free (no DRF):
pure business logic in the services layer.
"""

from __future__ import annotations

import hashlib

from accounts.enums import OrgType
from accounts.models import Organisation


def _normalise(name: str) -> str:
    """Casefold + collapse internal whitespace for case/space-insensitive dedup.

    `str.split()` with no args splits on any run of whitespace and drops empties,
    so `"  Dune   Travel "` and `"dune travel"` both normalise to `"dune travel"`.
    Preserves all characters (no slugify) so non-Latin names (e.g. Greek) survive.
    """
    return " ".join(name.split()).casefold()


def company_dedup_key(name: str) -> str:
    """The canonical content-hash dedup key for a company name.

    Pure and stdlib-only by design: the Unit-5b frozen migration that backfills
    an existing DB must compute the IDENTICAL key but cannot import app code, so
    it inlines this exact algorithm and a test pins the two together. This
    function is the single source of truth — change the algorithm here and the
    migration's inlined copy (+ its sync test) must change in lockstep.

    Caller must have already rejected blank names (see
    `organisation_for_company_name`).
    """
    digest = hashlib.sha1(_normalise(name).encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"org-{digest[:24]}"


def organisation_for_company_name(name: str | None) -> Organisation | None:
    """Get-or-create the agency Organisation for a free-text company string.

    Returns ``None`` for a blank/whitespace-only name — a company-less contact
    gets a null agency, never a junk org. The dedup key is a content hash of the
    normalised name (`dedup_key`, not `legacy_id`), so case/whitespace variants
    converge on one row and distinct names never collide even past the 64-char
    column limit (the hash is fixed-length). Idempotent given the unique
    `dedup_key`: a re-run returns the existing row. The display `name` keeps the
    first-seen original casing; near-duplicates are surfaced for human review by
    the `dedupe_organisations` command, never auto-merged here.
    """
    if not name or not name.strip():
        return None
    org, _ = Organisation.objects.get_or_create(
        dedup_key=company_dedup_key(name),
        defaults={"name": name.strip(), "org_type": OrgType.AGENCY},
    )
    return org
