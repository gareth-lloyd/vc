"""Small shared helpers for the legacy loaders."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from data_migration.base import legacy_datetime_literal


def legacy_row_deleted(row: dict[str, Any]) -> bool:
    """True when a legacy row is soft-deleted under EITHER convention.

    Legacy's own views (`vw_regions`, `vw_getRates`) key deletion on
    `ISNULL(DeletedBy,'') <> ''`; most Django loaders filter on
    `DeletedAt IS NULL`; the `sp_*` DELETE paths write both. OR-combining is
    a superset of both, so a row deleted through any path counts (GAP-107).
    Python twin of `legacy_deleted_sql` — keep the two in step.
    """
    if row.get("DeletedAt") is not None:
        return True
    return bool((row.get("DeletedBy") or "").strip())


def legacy_deleted_sql(alias: str = "") -> str:
    """SQL twin of `legacy_row_deleted`, for `reconcile_legacy` queries.

    `alias` is the table alias including its dot (`"r."`), or empty.
    """
    return f"({alias}DeletedAt IS NOT NULL OR ISNULL({alias}DeletedBy, '') <> '')"


def legacy_changed_since_sql(since: datetime) -> str:
    """`--since` predicate for legacy tables whose `sp_*` write paths stamp
    a DIFFERENT column per action: INSERT sets `CreatedAt`, UPDATE sets
    `UpdateAt` (no "d"), soft-DELETE sets only `DeletedAt`. Filtering on
    `UpdateAt` alone would miss exactly the rows a delta load exists to
    catch — the inserts and the deletions (GAP-107; `VillaRegion` /
    `VillaCountry`).
    """
    literal = legacy_datetime_literal(since)
    return f"(UpdateAt > '{literal}' OR DeletedAt > '{literal}' OR CreatedAt > '{literal}')"


def person_for_client(legacy_client_id: Any) -> Any:
    """Resolve the unified `Person` for a legacy VillaClientDetails id.

    GAP-045 D5-3: `ClientLoader` writes one `Person` per client keyed
    `legacy_id="client-{id}"`. Downstream loaders (booking / quotation /
    preference) call this to resolve their customer FK, replacing the old
    legacy-client → mirror-Person lookup the cutover retired.

    Sentinel FALLBACK over a bare `.get()`: `ClientLoader` skips the one
    documented no-name row, so a `.get()` would raise `DoesNotExist` and turn a
    previously-loaded downstream row into a silently-skipped error (new data
    loss). Per the sentinel-fallback convention we fall back to `unknown_client()`
    instead. Returns `None` only when no id was supplied (the caller early-returns
    a row with no client reference, mirroring the prior `guest is None` skip).
    """
    if not legacy_client_id:
        return None
    from accounts.models import Person
    from data_migration.loaders.sentinels import CLIENT_LEGACY_PREFIX, unknown_client

    person = Person.objects.filter(legacy_id=f"{CLIENT_LEGACY_PREFIX}{legacy_client_id}").first()
    if person is not None:
        return person
    return unknown_client()


def ensure_enquiry(person: Any, *, legacy_id: str, agent: Any | None = None) -> Any:
    """Idempotently back-create a minimal Enquiry for a Person (customer).

    Mirrors `QuotationService.minimal_enquiry_for` but keyed on `legacy_id` so
    re-running the import doesn't spawn duplicate enquiries. Used where a legacy
    quotation has no resolvable `EnquireId` (now that `Quotation.enquiry` is
    mandatory). Tagged `AGENT_PORTAL` for conversion-reporting segmentation.

    GAP-045 D5-3: takes the unified `person` (no longer a `Guest`) and sources
    the contact fields off the Person + its PRIMARY email/phone children; the
    legacy `guest=` write is dropped.
    """
    from reservations.enums import EnquirySource
    from reservations.models.enquiry import Enquiry

    primary_email = person.emails.filter(is_primary=True).first()
    primary_phone = person.phones.filter(is_primary=True).first()

    enquiry, _ = Enquiry.objects.update_or_create(
        legacy_id=legacy_id,
        defaults={
            "person": person,
            "first_name": person.first_name,
            "last_name": person.last_name,
            "email": primary_email.email if primary_email else "",
            "phone": primary_phone.number if primary_phone else "",
            "contact_method": person.preferred_method,
            "agent": agent,
            "site_source": EnquirySource.AGENT_PORTAL.value,
        },
    )
    return enquiry


def legacy_quotation_no(row: dict[str, Any]) -> int | None:
    """Parse the legacy `QuotationNo`, returning a positive int or `None`.

    `0`, NULL, negative, and non-numeric values all map to `None`, so the
    quotation and booking loaders interpret a missing/sentinel `QuotationNo`
    identically (avoiding the `QVC0` / `VC0` references a bare `int()` would
    have produced).
    """
    raw = row.get("QuotationNo")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None
