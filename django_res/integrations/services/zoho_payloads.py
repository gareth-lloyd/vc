"""Person → Zoho Flow contact payload builder (GAP-081).

Full-fat payload: every CRM-relevant `accounts.Person` field, JSON-safe
(datetime → ISO-8601), `RES_ID` + `id` on the record and on every nested
sub-object (agency, country, emails, phones). Upsert semantics in the Flow
are keyed on `RES_ID`.

Covers the legacy `ZohoContactPostData` minimum checklist
(`legacy/workflows/11-integrations/zoho-crm.md`: id, RES_ID, Email,
First_Name, Last_Name, Full_Name, Phone, Title, Mobile, Address_Line_1)
mapped onto current model fields — there is no `accounts.Contact` model.

Two deliberate exclusions (user decision 2026-07-23):
- `notes` is NEVER included — free-text operator notes stay internal.
- `tags` is filtered through the `SENSITIVE_TAGS` denylist below.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from accounts.enums import PersonTag, PhoneLabel
from accounts.models import Organisation, Person, PersonEmail, PersonPhone

# GAP-040 tag taxonomy (`accounts.enums.PersonTag`) carries two
# special-category / duty-of-care markers that must never leave res —
# `Person.anonymize()` already treats exactly these as special-category data
# (it scrubs `tags` from the audit trail because "disability was added" would
# stay recoverable). The remaining tags (VIP / Trade / PA / Nick's … /
# Past issues / Specific preferences / Time waster) are ordinary operator
# flags and push in clear.
SENSITIVE_TAGS: frozenset[str] = frozenset(
    {
        PersonTag.DISABILITY.value,
        PersonTag.APPROACH_WITH_CARE.value,
    }
)


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _country_payload(country: Any) -> dict[str, Any] | None:
    # Duck-typed `properties.Country`: `properties` sits ABOVE `integrations`
    # in the import spine, so this module must not import it (even under
    # TYPE_CHECKING — import-linter counts those).
    if country is None:
        return None
    return {
        "RES_ID": country.pk,
        "id": country.pk,
        "name": country.name,
        "iso2": country.iso2,
        "iso3": country.iso3,
    }


def _agency_payload(agency: Organisation | None) -> dict[str, Any] | None:
    if agency is None:
        return None
    return {
        "RES_ID": agency.pk,
        "id": agency.pk,
        "name": agency.name,
        "org_type": agency.org_type,
        "email": agency.email,
        "phone": agency.phone,
        "address_line_1": agency.address_line_1,
        "address_line_2": agency.address_line_2,
        "town": agency.town,
        "post_code": agency.post_code,
        "country": _country_payload(agency.country),
        "website_url": agency.website_url,
        "status": agency.status,
    }


def _email_payload(email: PersonEmail) -> dict[str, Any]:
    return {
        "RES_ID": email.pk,
        "id": email.pk,
        "email": email.email,
        "label": email.label,
        "is_primary": email.is_primary,
    }


def _phone_payload(phone: PersonPhone) -> dict[str, Any]:
    return {
        "RES_ID": phone.pk,
        "id": phone.pk,
        "number": phone.number,
        "label": phone.label,
        "is_primary": phone.is_primary,
    }


def build_person_payload(person: Person) -> dict[str, Any]:
    """Full-field JSON-safe contact payload for one `accounts.Person`.

    Built at push time from the live row. The anonymized-skip lives upstream
    (`enqueue_zoho_push` / `push_sync_record`), not here.
    """
    emails = list(person.emails.all())
    phones = list(person.phones.all())
    mobiles = [p.number for p in phones if p.label == PhoneLabel.MOBILE and p.number]
    return {
        "RES_ID": person.pk,
        "id": person.pk,
        "legacy_id": person.legacy_id,
        "title": person.title,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "full_name": person.display_name or "",
        "agency": _agency_payload(person.agency),
        "website_url": person.website_url,
        "preferred_method": person.preferred_method,
        "address_line_1": person.address_line_1,
        "address_line_2": person.address_line_2,
        "town": person.town,
        "post_code": person.post_code,
        "country": _country_payload(person.country),
        "marketing_consent": person.marketing_consent,
        "tags": [tag for tag in person.tags if tag not in SENSITIVE_TAGS],
        "status": person.status,
        "kind": person.kind,
        "primary_email": person.primary_email(),
        "primary_phone": person.primary_phone(),
        "mobile": mobiles[0] if mobiles else None,
        "emails": [_email_payload(e) for e in emails],
        "phones": [_phone_payload(p) for p in phones],
        "created_at": _iso(person.created_at),
        "updated_at": _iso(person.updated_at),
    }
