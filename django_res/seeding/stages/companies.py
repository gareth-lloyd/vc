"""Seed a pool of `accounts.Organisation` (B2B companies) so the Companies
directory screen and the contact→agency filter have data in dev/staging.

`OrganisationViewSet` partitions by `org_type`: AGENCY backs the B2B Companies
directory (GAP-046), MANAGEMENT_COMPANY surfaces as a property assignee, and
SUPPLIER is a concierge supplier. The pool is agency-dominant but always carries
at least one SUPPLIER and one MANAGEMENT_COMPANY once it holds ≥3, and a couple
are INACTIVE, so every org_type screen and the status filter have data to demo.

Deterministic by construction (index-driven, no RNG) — like the `owner_orgs`
fixture, the Companies directory is reproducible rather than seed-varying, and
the type/status spread is guaranteed instead of left to chance. Names fold the
per-process `RUN_TOKEN` (mirroring `properties.factories.villa_name`) so an
additive reseed in a fresh process draws a different slice of the name space and
never collides on email/website.

Distinct from the `owner_orgs` stage, which seeds the owner-portal
`OwnerOrganisation` login tenant — a different model. The shared
`OrganisationFactory` is intentionally left untouched (its defaults are shared
with ~40 tests); the stage passes explicit realistic fields instead.
"""

from __future__ import annotations

from django.utils.text import slugify

from accounts.enums import OrgStatus, OrgType
from accounts.factories import OrganisationFactory
from core.factories import RUN_TOKEN
from seeding.context import SeedContext
from seeding.registry import Stage, register

# Curated word menus → deterministic, human-readable names (no faker, so the
# output is stable and self-contained). `_FIRST` has ≥14 distinct entries so the
# largest pool (chaos, 14) gets a distinct first word per org, hence distinct
# names / emails.
_FIRST = [
    "Azure",
    "Coastal",
    "Meridian",
    "Aegean",
    "Sunstone",
    "Olive Grove",
    "Harbour",
    "Cypress",
    "Bluewater",
    "Ionian",
    "Riviera",
    "Summit",
    "Kastro",
    "Verano",
    "Alpine",
]
# Suffix paired with the org_type it reads naturally for.
_SUFFIX = {
    OrgType.AGENCY: ["Travel", "Villas", "Escapes", "Holidays", "Retreats"],
    OrgType.MANAGEMENT_COMPANY: ["Management", "Estates", "Property Group", "Hospitality"],
    OrgType.SUPPLIER: ["Concierge", "Services", "Provisions", "Transfers"],
}
_TOWNS = [
    "Athens",
    "Mykonos",
    "Nice",
    "Marbella",
    "Palma",
    "Corfu",
    "Chania",
    "Sorrento",
    "Bodrum",
    "London",
]

# Fold RUN_TOKEN so separate seed_dev processes draw a different slice of the
# name space (mirrors properties.factories.villa_name), keeping additive reseeds
# from colliding on email/website. RUN_TOKEN is hex.
_OFFSET = int(RUN_TOKEN, 16)


def _org_type_for(index: int) -> OrgType:
    """Agency-dominant, but guarantee one SUPPLIER and one MANAGEMENT_COMPANY as
    soon as the pool is large enough, so all three org_type screens have data."""
    if index == 1:
        return OrgType.SUPPLIER
    if index == 2:
        return OrgType.MANAGEMENT_COMPANY
    return OrgType.AGENCY


def _run(ctx: SeedContext) -> int:
    n = ctx.knobs.n_organisations
    if n <= 0:
        return 0

    # A couple INACTIVE (scaled with the pool) to demo the status filter; the
    # rest ACTIVE so the dominant cohort is guaranteed.
    n_inactive = min(2, n // 4)

    for i in range(n):
        org_type = _org_type_for(i)
        first = _FIRST[(i + _OFFSET) % len(_FIRST)]
        suffixes = _SUFFIX[org_type]
        name = f"{first} {suffixes[(i + _OFFSET) % len(suffixes)]}"
        # RUN_TOKEN keeps email/website unique across additive reseeds.
        domain = f"{slugify(name)}-{RUN_TOKEN}"
        status = OrgStatus.INACTIVE if i >= n - n_inactive else OrgStatus.ACTIVE
        org = OrganisationFactory(
            name=name,
            org_type=org_type,
            status=status,
            email=f"hello@{domain}.example.com",
            town=_TOWNS[(i + _OFFSET) % len(_TOWNS)],
            website_url=f"https://{domain}.example.com",
        )
        ctx.organisations.append(org)

    return n


register(Stage(name="companies", run=_run))
