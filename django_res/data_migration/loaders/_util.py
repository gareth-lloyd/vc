"""Small shared helpers for the legacy loaders."""

from __future__ import annotations

from typing import Any

import phonenumbers
import structlog

from reservations.phone import region_from_calling_code, to_e164

logger = structlog.get_logger(__name__)

# BUG-030 §8: legacy `VillaRegion` 25 "The Peloponnesse" and 27 "Midi-Pyrenese"
# are misspelt twins of 61 "Peloponnese" and 60 "Midi-Pyrenees", retired
# 2024-11 when the corrected rows were created — no name-level rule can find
# them, hence the explicit map. The villas filed under the duplicates belong
# on the live twin. Applied wherever a loader resolves a legacy region id
# (Property, Enquiry). 47 "The Peloponesse" (same retirement) has no villas
# and stays unmapped per the ticket decision; the runtime WordPress intake
# resolves live WP ids and is deliberately untouched.
LEGACY_REGION_REMAP: dict[str, str] = {"25": "61", "27": "60"}

# BUG-030 §6 — the two loader-side "England is GB" tables (the sheet
# importers have their own name-keyed `sheets.matching.COUNTRY_ALIASES`).
#
# Non-ISO codes legacy stores in `VillaCountry.ShortName1` for a real country.
LEGACY_ISO2_ALIASES: dict[str, str] = {"UK": "GB"}
# Legacy `VillaCountry` 24 ("England", ShortName1 `UK`, deleted) duplicates 6
# ("United Kingdom", no iso code, deleted). Both resolve to GB and only one
# legacy id can sit on the GB seed row (6 claims it first, in Id order), so
# `CountryLoader` skips 24 and its FK consumers resolve it here — no
# post-load `merge_country` step (the retired CUTOVER §7). The other deleted
# twins, 13 France and 20 India, are deliberately NOT aliased: FR and IN are
# live, so their regions would load active and move the calibrated
# `Region (active)` gap — a GAP-108 decision, made on the live dump.
LEGACY_COUNTRY_ALIASES: dict[str, str] = {"24": "GB"}


def country_for_legacy_id(legacy_country_id: str) -> Any:
    """The loaded `Country` for a legacy `VillaCountry.Id`: the row stamped
    with that `legacy_id`, else the `LEGACY_COUNTRY_ALIASES` iso2 row, else
    `None` (callers fall back to `unknown_country()` or leave it null)."""
    from properties.models.geo import Country

    if not legacy_country_id:
        return None
    country = Country.objects.filter(legacy_id=legacy_country_id).first()
    if country is None:
        iso2 = LEGACY_COUNTRY_ALIASES.get(legacy_country_id)
        if iso2 is not None:
            logger.info(
                "data_migration.country_aliased",
                legacy_country_id=legacy_country_id,
                aliased_to=iso2,
            )
            country = Country.objects.filter(iso2=iso2).first()
    return country


def region_for_legacy_id(legacy_region_id: str, **log_context: Any) -> Any:
    """The loaded `Region` for a legacy `VillaRegions.Id`, following
    `LEGACY_REGION_REMAP` (logged, with the caller's context) — `None` when
    nothing is loaded under that id."""
    from properties.models.geo import Region

    if not legacy_region_id:
        return None
    target = LEGACY_REGION_REMAP.get(legacy_region_id)
    if target is not None:
        logger.info(
            "data_migration.region_remapped",
            legacy_region_id=legacy_region_id,
            remapped_to=target,
            **log_context,
        )
        legacy_region_id = target
    return Region.objects.filter(legacy_id=legacy_region_id).first()


def legacy_phone(number: object, calling_code: object) -> str:
    """BUG-030 §17: one rule for a legacy (calling code, national number) pair.

    The calling code anchors the number (dump shapes: "0044"+"7770302297",
    "44"+"07771950930"); a row with no readable code is a UK number. A number
    that still fails validation keeps its calling code (`+30 12345`) so the
    country isn't lost; with no code it passes through trimmed (`to_e164`).
    Truncated to the 32-char phone columns.
    """
    cc_region = region_from_calling_code(str(calling_code or ""))
    full = to_e164(str(number or ""), region=cc_region or "GB")
    if full and cc_region and not full.startswith("+"):
        full = f"+{phonenumbers.country_code_for_region(cc_region)} {full}"
    return full[:32]


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


def legacy_active_sql(alias: str = "") -> str:
    """`IsActive` soft-delete filter (GAP-108), for loader and reconcile SQL.

    ResProd's DELETE paths (`sp_crud_VillaRooms`, `SP_CRUD_VILLA_FEATURES_TAGS`,
    `SP_CRUD_PropertyNearByLocationType`) set `IsActive = 0`, and its views keep
    only `isnull(IsActive,0) = 1` — NULL counts as inactive. `alias` as for
    `legacy_deleted_sql`.
    """
    return f"ISNULL({alias}IsActive, 0) = 1"


def live_villa_sql(alias: str = "") -> str:
    """`VillaMaster` rows PropertyLoader loads (GAP-108): live AND a non-blank
    `Name` (the loader skips a blank one — villa 249 on the 24-Apr-2025 dump,
    543 on ResProd). Shared by the loader and every reconcile query scoped to
    loaded villas. `alias` as for `legacy_deleted_sql`.
    """
    return f"{alias}DeletedAt IS NULL AND LEN(LTRIM(RTRIM(ISNULL({alias}Name, '')))) > 0"


def legacy_currency_for(row: dict[str, Any], prop: Any) -> Any:
    """The GAP-014 currency chain shared by every loader that carries a
    legacy `CurrencyId`: the row's currency when set and known, else the
    villa's canonical chain (`resolve_property_currency`: preferred live
    plan → settings → EUR) — never the ordering-dependent `.first()`.
    Returns `None` when nothing resolves; each caller decides how to skip.
    """
    from pricing.models.currency import Currency
    from pricing.services.currency import resolve_property_currency

    currency = None
    if row.get("CurrencyId"):
        currency = Currency.objects.filter(legacy_id=str(row["CurrencyId"])).first()
    if currency is None:
        currency = resolve_property_currency(prop)
    return currency


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


def legacy_aware(value: Any) -> Any:
    """A legacy SQL Server datetime (naive) made aware in the default zone."""
    from django.utils import timezone

    return timezone.make_aware(value) if timezone.is_naive(value) else value


def ensure_enquiry(
    person: Any,
    *,
    legacy_id: str,
    agent: Any | None = None,
    site_source: str | None = None,
    created_at: Any | None = None,
    note: str = "",
) -> Any:
    """Idempotently back-create a minimal Enquiry for a Person (customer).

    Mirrors `QuotationService.minimal_enquiry_for` but keyed on `legacy_id` so
    re-running the import doesn't spawn duplicate enquiries. Used where a legacy
    quotation has no resolvable `EnquireId` (now that `Quotation.enquiry` is
    mandatory). Tagged `AGENT_PORTAL` by default for conversion-reporting
    segmentation; BUG-030 §24: an agent-less quotation's stand-in passes
    `site_source=OTHER`, its quotation's `created_at` (back-stamped past
    `auto_now_add`) and a provenance `note` (the `inbound_message`).

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
            "site_source": site_source or EnquirySource.AGENT_PORTAL.value,
            "inbound_message": note,
        },
    )
    if created_at is not None:
        Enquiry.objects.filter(pk=enquiry.pk).update(created_at=created_at)
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
