"""Enquiry → Zoho Flow payload builder (GAP-081 Unit 2).

Full-fat, JSON-safe payload (dates → ISO-8601), `RES_ID` + `id` on the record
and on every nested sub-object (person, agent, property, region, country).
Upsert semantics in the Flow are keyed on `RES_ID`.

Covers the legacy `ZohoEnquiryPostData` minimum checklist
(`legacy/workflows/11-integrations/zoho-crm.md`), snake_case, mapped onto the
current models: Name/Payment_Contact→`full_name`, Date_From/To→`date_from`/
`date_to`, Length_of_Stay→`nights`, Bedrooms_From/To→`min_bedrooms`,
Number_of_Adults/Children→`adults`/`children`, Stage→`status` (+
`lead_status`), Agency/Agent→`agent` sub-object, Enquiry_Notes→
`inbound_message` (the guest's own message — operator `EnquiryNote` rows stay
internal), Enquiry_Source→`site_source`, Countries/Regions_of_Interest→
`region` sub-object (single FK on the current model),
Where_did_you_hear_from_us→`referral_code`, Contact→`person` sub-object,
Villa→`property` sub-object, Owner→`assigned_to` sub-object. `Zoho_ID`
(external id) has no current-model equivalent and is omitted.

`assigned_to` (the current owner/routing column — the modern analogue of the
legacy hardcoded `Owner` mailbox) is a compact staff sub-object, None when
unassigned.

Person/agent sub-objects are compact summaries (the full contact record is
pushed separately via the `contact` kind). Erasure: an ANONYMIZED Person is
omitted entirely so its [REDACTED] sentinels never leak into the CRM, and the
enquiry's own denormalised capture columns (first/last name, email, phone) —
which `Person.anonymize()` does not scrub — are blanked in the payload when
the linked person is anonymized. NB an enquiry with NO linked Person has no
erasure hook at all (pre-existing: Enquiry has no erasure path) — that
residual gap is out of scope here.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from integrations.services.zoho_flow import is_anonymized_person

if TYPE_CHECKING:
    from accounts.models import Person
    from properties.models.geo import Region
    from properties.models.property import Property
    from reservations.models import Enquiry


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _person_summary(person: Person | None) -> dict[str, Any] | None:
    if person is None or is_anonymized_person(person):
        return None
    return {
        "RES_ID": person.pk,
        "id": person.pk,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "full_name": person.display_name or "",
        "agency_name": person.agency_name,
        "primary_email": person.primary_email(),
        "primary_phone": person.primary_phone(),
    }


def _assigned_to_payload(user: Any) -> dict[str, Any] | None:
    """Compact staff sub-object for `Enquiry.assigned_to` (duck-typed
    `accounts.User`). Staff identity, not customer PII."""
    if user is None:
        return None
    return {
        "id": user.pk,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": f"{user.first_name} {user.last_name}".strip(),
        "email": user.email,
    }


def _region_payload(region: Region | None) -> dict[str, Any] | None:
    if region is None:
        return None
    country = region.country
    return {
        "RES_ID": region.pk,
        "id": region.pk,
        "name": region.name,
        "country": {
            "RES_ID": country.pk,
            "id": country.pk,
            "name": country.name,
            "iso2": country.iso2,
        },
    }


def _property_payload(prop: Property | None) -> dict[str, Any] | None:
    if prop is None:
        return None
    return {
        "RES_ID": prop.pk,
        "id": prop.pk,
        "name": prop.name,
        "display_name": prop.display_name,
        "slug": prop.slug,
        "region": _region_payload(prop.region),
    }


def build_enquiry_payload(enquiry: Enquiry) -> dict[str, Any]:
    """Full-field JSON-safe payload for one `reservations.Enquiry`.

    Built at push time from the live row (see
    `integrations.tasks.push_sync_record`).
    """
    person_summary = _person_summary(enquiry.person)
    # The linked person was erased but the enquiry's own capture columns are
    # not touched by `Person.anonymize()` — blank them here so a later save
    # or backfill can't re-export the erased person's PII.
    person_erased = enquiry.person is not None and is_anonymized_person(enquiry.person)
    nights = (
        (enquiry.date_to - enquiry.date_from).days
        if enquiry.date_from is not None and enquiry.date_to is not None
        else None
    )
    denormalised_name = f"{enquiry.first_name} {enquiry.last_name}".strip()
    full_name = (person_summary or {}).get("full_name") or denormalised_name
    return {
        "RES_ID": enquiry.pk,
        "id": enquiry.pk,
        "reference": enquiry.reference,
        "legacy_id": enquiry.legacy_id,
        # Denormalised capture fields (pre-Person / anonymous submissions).
        "first_name": "" if person_erased else enquiry.first_name,
        "last_name": "" if person_erased else enquiry.last_name,
        "email": "" if person_erased else enquiry.email,
        "phone": "" if person_erased else enquiry.phone,
        "contact_method": enquiry.contact_method,
        "full_name": "" if person_erased else full_name,
        "person": person_summary,
        "agent": _person_summary(enquiry.agent),
        "assigned_to": _assigned_to_payload(enquiry.assigned_to),
        "property": _property_payload(enquiry.property),
        "region": _region_payload(enquiry.region),
        "date_from": _iso(enquiry.date_from),
        "date_to": _iso(enquiry.date_to),
        "nights": nights,
        "is_flexible": enquiry.is_flexible,
        "flexibility_days": enquiry.flexibility_days,
        "adults": enquiry.adults,
        "children": enquiry.children,
        "min_bedrooms": enquiry.min_bedrooms,
        "request_type": enquiry.request_type,
        "referral_code": enquiry.referral_code,
        "site_source": enquiry.site_source,
        "status": enquiry.status,
        "lost_reason": enquiry.lost_reason,
        "lead_status": enquiry.lead_status,
        "inbound_message": enquiry.inbound_message,
        "created_at": _iso(enquiry.created_at),
        "updated_at": _iso(enquiry.updated_at),
    }
