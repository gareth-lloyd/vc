"""Enquiry + Quotation → Zoho Flow payload builders (GAP-081 Units 2-3).

Full-fat, JSON-safe payload (dates → ISO-8601), `RES_ID` + `id` on the record
and on every nested sub-object (person, agent, property, region, country).
Upsert semantics in the Flow are keyed on `RES_ID`.

Covers the legacy `ZohoEnquiryPostData` minimum checklist
(`legacy/workflows/11-integrations/zoho-crm.md`), snake_case, mapped onto the
current models: Name/Payment_Contact→`full_name`, Date_From/To→`date_from`/
`date_to`, Length_of_Stay→`nights`, Bedrooms_From/To→`min_bedrooms`,
Number_of_Adults/Children→`adults`/`children`, Stage→`status` (+
`lead_status`), Agency/Agent→`agent` sub-object, Enquiry_Notes→
`inbound_message` (the guest's own message; operator `EnquiryNote` rows push
as the separate `notes` list — included since 2026-07-23, superseding the
original stay-internal decision, each row keyed by `RES_ID` for Zoho-side
dedupe), Enquiry_Source→`site_source`, Countries/Regions_of_Interest→
`region` sub-object (single FK on the current model),
Where_did_you_hear_from_us→`referral_code`, Contact→`person` sub-object,
Villa→`property` sub-object, Owner→`assigned_to` sub-object. `Zoho_ID`
(external id) has no current-model equivalent and is omitted.

`assigned_to` (the current owner/routing column — the modern analogue of the
legacy hardcoded `Owner` mailbox) is a compact staff sub-object, None when
unassigned.

Person/agent sub-objects are compact summaries (the full contact record is
pushed separately via the `contact` kind), plus a keyed `agency` sub-object so
Flow can join the agent to its agency record, not just string-match
`agency_name`. Erasure: an ANONYMIZED Person is omitted entirely so its
[REDACTED] sentinels never leak into the CRM, and the enquiry's own
denormalised capture columns (first/last name, email, phone) — which
`Person.anonymize()` does not scrub — are blanked in the payload when the
linked person is anonymized; the `notes` list is blanked too (operator free
text routinely names the guest and cannot be selectively scrubbed). An
anonymized AGENT only nulls the `agent` sub-object — the notes still push
(blanking a live guest's enquiry notes because the agent was erased is the
wrong trade; accepted residual, same class as the next). NB an enquiry with
NO linked Person has no erasure hook at all (pre-existing: Enquiry has no
erasure path) — that residual gap is out of scope here.

`build_quotation_payload` covers the legacy `QuotationPostData` checklist:
Name/Account/Contact→`full_name` + `person` sub-object, Stage→`status`,
Valid_Until→`expires_at`, Enquiry.RES_ID→`enquiry` sub-object,
Terms_and_Conditions→`terms_version` sub-object; Arrival_Date/Departure_Date/
No_of_Nights/No_of_Guests/Country/Region/Villa/Currency/Line_Items live
per-LINE on the current model (a quote is multi-option) → `lines[]`, `.real()`
only (booking-synthesised rows are an internal fill artefact and never leave
res), each with its property sub-object, ISO dates, currency code, money as
strings (Decimal→str) and the full `pricing_snapshot`. The legacy money-split
fields (Deposit_Amount / Balance_Amount / Commission_* / Security_Deposit_* /
Net_Booking / Cost_of_Sale) are booking/payment-domain figures the legacy
computed from its finance view at push time — they have no Quotation-model
source and ship with the ~Sept booking build (`booking` kind), not here.
`Zoho_ID` is omitted (external ids stay blank by contract).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from integrations.services.zoho_flow import is_anonymized_person

if TYPE_CHECKING:
    from accounts.models import Person
    from properties.models.geo import Region
    from properties.models.property import Property
    from reservations.models import Enquiry, Quotation
    from reservations.models.enquiry import EnquiryNote
    from reservations.models.quotation import QuotationLine


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
        "agency": (
            {"RES_ID": person.agency.pk, "id": person.agency.pk, "name": person.agency.name}
            if person.agency is not None
            else None
        ),
        "primary_email": person.primary_email(),
        "primary_phone": person.primary_phone(),
    }


def _note_payload(note: EnquiryNote) -> dict[str, Any]:
    return {
        "RES_ID": note.pk,
        "id": note.pk,
        "kind": note.kind,
        "body": note.body,
        "is_pinned": note.is_pinned,
        "author": _assigned_to_payload(note.author),
        "created_at": _iso(note.created_at),
        "updated_at": _iso(note.updated_at),
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
        "notes": (
            []
            if person_erased
            else [_note_payload(note) for note in enquiry.notes_collection.select_related("author")]
        ),
        "created_at": _iso(enquiry.created_at),
        "updated_at": _iso(enquiry.updated_at),
    }


def _line_payload(line: QuotationLine) -> dict[str, Any]:
    return {
        "RES_ID": line.pk,
        "id": line.pk,
        "legacy_id": line.legacy_id,
        "property": _property_payload(line.property),
        "currency": line.currency.code,
        "date_from": _iso(line.date_from),
        "date_to": _iso(line.date_to),
        "nights": (line.date_to - line.date_from).days,
        "adults": line.adults,
        "children": line.children,
        # Money as strings: Decimals are not JSON-serialisable, floats drift.
        "total": str(line.total),
        "discount": str(line.discount),
        "pricing_snapshot": line.pricing_snapshot,
        "inclusions": line.inclusions,
        "price_override_reason": line.price_override_reason,
        "is_selected": line.is_selected,
        "is_manual": line.is_manual,
        "notes": line.notes,
    }


def build_quotation_payload(quotation: Quotation) -> dict[str, Any]:
    """Full-field JSON-safe payload for one `reservations.Quotation`.

    Built at push time from the live row. `.real()` lines only — the
    booking-synthesised fill rows never leave res. The header carries no
    currency by design (GAP-014: per-line currency, mixed currencies are
    expected and not normalised).
    """
    person_summary = _person_summary(quotation.person)
    person_erased = is_anonymized_person(quotation.person)
    full_name = "" if person_erased else ((person_summary or {}).get("full_name") or "")
    enquiry = quotation.enquiry
    lines = quotation.lines.real().select_related("property__region__country", "currency")
    return {
        "RES_ID": quotation.pk,
        "id": quotation.pk,
        "reference": quotation.reference,
        "number": quotation.number,
        "legacy_id": quotation.legacy_id,
        "full_name": full_name,
        "person": person_summary,
        "agent": _person_summary(quotation.agent),
        "enquiry": (
            {"RES_ID": enquiry.pk, "id": enquiry.pk, "reference": enquiry.reference}
            if enquiry is not None
            else None
        ),
        "status": quotation.status,
        "is_unbranded": quotation.is_unbranded,
        "cancel_reason": quotation.cancel_reason,
        "expires_at": _iso(quotation.expires_at),
        "terms_version": {
            "RES_ID": quotation.terms_version_id,
            "id": quotation.terms_version_id,
            "version": quotation.terms_version.version,
        },
        "lines": [_line_payload(line) for line in lines],
        "created_at": _iso(quotation.created_at),
        "updated_at": _iso(quotation.updated_at),
    }
