"""Create an Enquiry from a WordPress-posted legacy payload.

Mapping philosophy: never lose a lead. Anything the model can't represent
(multi-property CSV, unknown legacy ids, out-of-range flexibility, wishlist
request type, marketing-attribution answers) is preserved as a bracketed
suffix line on `inbound_message` rather than dropped or rejected. Villa /
region / country resolution goes through `legacy_id` — the WP site sends
numeric ResSystem ids (with `0` / `"0"` meaning "none selected"), the same
bridge the data-migration loaders use.

`handle_wordpress_enquiry` is the endpoint's whole business layer: dedupe via
the `IntegrationInboundCall` record-or-replay ledger keyed by
`derive_idempotency_key` over the *validated* payload (so undeclared keys the
serializer ignores — nonces, timestamps — can't defeat dedupe), plus one
AuditLog row per handled call. The audit write sits after the ledger commit:
best-effort — a crash in between loses only the audit row, never the lead
(the WP retry replays and audits).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from core.models import AuditLog
from core.request_context import get_correlation_id
from integrations.enums import SyncProvider
from integrations.models import IntegrationInboundCall
from integrations.services.inbound import record_or_replay
from properties.models import Country, Property, Region
from reservations.enums import EnquiryRequestType, EnquirySource
from reservations.models import Enquiry
from reservations.phone import to_e164

if TYPE_CHECKING:
    from accounts.models import User

logger = structlog.get_logger(__name__)

# Enquiry.flexibility_days's validator caps at 3 (only enforced via
# full_clean, so the clamp here is load-bearing, not belt-and-braces).
_MAX_FLEXIBILITY_DAYS = 3

# The wire truth (vc_wp_1.sql, 201 submissions): the STRING is authoritative
# and carries UI labels; the int EnquireDateType is unreliable (7 accompanies
# both "Specific dates" and "Flexible"). Legacy .NET enum names kept as
# fallback tolerance. Values are flexibility day-counts pre-clamp.
_FLEX_DAYS_BY_LABEL = {
    # Real wire labels.
    "specific dates": 0,
    "+/- 3 days": 3,
    "flexible": 30,
    # Legacy EDate_Type enum names (DTO/Postman variants).
    "unknown": 0,
    "specificdays": 0,
    "threedays": 3,
    "sevendays": 7,
    "wholedays": 30,
}
# Int wire value -> legacy enum name, used only when no string is present.
_DATE_TYPE_NAMES = {
    0: "Unknown",
    1: "SpecificDays",
    3: "ThreeDays",
    7: "SevenDays",
    30: "WholeDays",
}


def derive_idempotency_key(payload: dict[str, Any], *, now: datetime | None = None) -> str:
    """Server-derived key: the legacy payload carries no client key.

    SHA-256 of the canonicalised payload plus a one-hour UTC time bucket, so
    same-payload retries within the bucket dedupe (a retry pair straddling
    the top of the hour still double-writes — accepted; retry storms are
    seconds apart) while a genuine identical re-enquiry in a later hour is a
    fresh lead.
    """
    moment = (now or timezone.now()).astimezone(UTC)
    bucket = moment.strftime("%Y%m%dT%H")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(f"{bucket}:{canonical}".encode()).hexdigest()
    return f"wp-{bucket}-{digest}"


def _resolve_property(data: dict[str, Any], leftovers: list[str]) -> Property | None:
    """Single numeric id -> `Property.legacy_id` lookup; anything else preserved."""
    raw: str = ""
    if data.get("PropertyId"):  # 0 is the WP "none selected" sentinel
        raw = str(data["PropertyId"])
    elif (data.get("Properties") or "").strip():
        raw = data["Properties"].strip()
    if not raw or raw == "0":
        return None
    if raw.isdigit():
        villa = Property.objects.filter(legacy_id=raw).first()
        if villa is not None:
            return villa
    leftovers.append(f"[property: {raw}]")
    return None


def _resolve_region(data: dict[str, Any], leftovers: list[str]) -> Region | None:
    region_ids = [r for r in (data.get("RegionIds") or []) if r]  # 0 = none selected
    if not region_ids:
        return None
    if len(region_ids) == 1:
        region = Region.objects.filter(legacy_id=str(region_ids[0])).first()
        if region is not None:
            return region
    leftovers.append(f"[regions: {','.join(str(r) for r in region_ids)}]")
    return None


def _preserve_countries(data: dict[str, Any], leftovers: list[str]) -> None:
    """Enquiry has no country field — resolve names where possible, keep raw."""
    raw_ids = [
        part.strip()
        for part in (data.get("CountryIds") or "").split(",")
        if part.strip() and part.strip() != "0"
    ]
    if not raw_ids:
        return
    names = {c.legacy_id: c.name for c in Country.objects.filter(legacy_id__in=raw_ids)}
    leftovers.append(f"[countries: {', '.join(names.get(i, i) for i in raw_ids)}]")


def _resolve_flexibility(data: dict[str, Any], leftovers: list[str]) -> tuple[bool, int]:
    raw = (data.get("EnquireDateTypeString") or "").strip()
    if not raw and data.get("EnquireDateType") is not None:
        raw = _DATE_TYPE_NAMES.get(data["EnquireDateType"], str(data["EnquireDateType"]))
    if not raw:
        return False, 0
    days = _FLEX_DAYS_BY_LABEL.get(raw.lower())
    if days is None:
        # Unrecognised value — assume fixed dates, keep the raw for a human.
        leftovers.append(f"[date flexibility: {raw}]")
        return False, 0
    if days > _MAX_FLEXIBILITY_DAYS:
        leftovers.append(f"[date flexibility: {raw}]")
        return True, _MAX_FLEXIBILITY_DAYS
    return days > 0, days


def _resolve_request_type(data: dict[str, Any], leftovers: list[str]) -> str:
    raw = (data.get("RequestType") or "").strip()
    if not raw or raw.upper() == "ENQUIRY":
        return EnquiryRequestType.QUOTE
    # WISHLIST and anything the enum can't represent — OTHER, raw preserved.
    leftovers.append(f"[request type: {raw}]")
    return EnquiryRequestType.OTHER


def _clean(data: dict[str, Any], key: str, max_length: int) -> str:
    return (data.get(key) or "").strip()[:max_length]


def create_enquiry_from_wordpress(data: dict[str, Any]) -> Enquiry:
    """`data` is `WordPressEnquirySerializer.validated_data`."""
    leftovers: list[str] = []

    villa = _resolve_property(data, leftovers)
    region = _resolve_region(data, leftovers)
    _preserve_countries(data, leftovers)
    is_flexible, flexibility_days = _resolve_flexibility(data, leftovers)
    request_type = _resolve_request_type(data, leftovers)

    date_from = data.get("FromDate")
    date_to = data.get("ToDate")
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    for key, label in (
        ("CountryId", "country"),
        ("Countries", "countries"),
        ("Regions", "region names"),
    ):
        if (data.get(key) or "").strip():
            leftovers.append(f"[{label}: {data[key].strip()}]")
    if data.get("MaxBed"):
        leftovers.append(f"[max bedrooms: {data['MaxBed']}]")
    if (data.get("UserFeedback") or "").strip():
        leftovers.append(f"[heard via: {data['UserFeedback'].strip()}]")
    # other_text is the free-text half of "how did you hear about us"; the WP
    # form defaults it to the literal "Other", which says nothing.
    other_text = (data.get("other_text") or "").strip()
    if other_text and other_text.lower() != "other":
        leftovers.append(f"[heard via detail: {other_text}]")
    if data.get("IsSignUp"):
        leftovers.append("[marketing opt-in: yes]")

    message_parts = [p for p in ((data.get("Notes") or "").strip(), *leftovers) if p]

    kwargs: dict[str, Any] = {
        "person": None,
        "first_name": _clean(data, "FirstName", 128),
        "last_name": _clean(data, "LastName", 128),
        "email": _clean(data, "Email", 254),
        "phone": to_e164(data.get("ContactNo"), country_code=data.get("CountryCode"))[:32],
        "property": villa,
        "region": region,
        "date_from": date_from,
        "date_to": date_to,
        "is_flexible": is_flexible,
        "flexibility_days": flexibility_days,
        "request_type": request_type,
        "referral_code": _clean(data, "referral", 64),
        "site_source": EnquirySource.MAIN_WEBSITE,
        "inbound_message": "\n".join(message_parts),
    }
    if data.get("MinBed") is not None:
        kwargs["min_bedrooms"] = data["MinBed"]
    if data.get("Adults") is not None:
        kwargs["adults"] = data["Adults"]
    if data.get("Children") is not None:
        kwargs["children"] = data["Children"]

    # Atomic so the Zoho auto-push SyncRecord (post_save) commits with the
    # enquiry — a failure there must not leave a half-created lead behind.
    with transaction.atomic():
        enquiry = Enquiry.objects.create(**kwargs)
    logger.info(
        "reservations.enquiry.wordpress_intake_created",
        enquiry_id=enquiry.pk,
        property_id=villa.pk if villa else None,
        unmapped_count=len(leftovers),
    )
    return enquiry


def handle_wordpress_enquiry(
    validated_data: dict[str, Any], *, actor: User
) -> IntegrationInboundCall:
    """Create-or-replay one inbound WP enquiry call and audit it."""

    def produce() -> tuple[int, dict[str, Any]]:
        enquiry = create_enquiry_from_wordpress(validated_data)
        return 201, {"reference": enquiry.reference}

    call, replayed = record_or_replay(
        provider=SyncProvider.WORDPRESS_SITE,
        idempotency_key=derive_idempotency_key(dict(validated_data)),
        produce=produce,
    )
    AuditLog.objects.create(
        content_type=ContentType.objects.get_for_model(IntegrationInboundCall),
        object_id=str(call.pk),
        actor=actor,
        field_diffs={
            "replayed": [None, replayed],
            "response_status": [None, call.response_status],
        },
        correlation_id=get_correlation_id(),
    )
    return call
