"""Person → Zoho Flow contact payload builder (GAP-081).

Full-fat payload: every CRM-relevant `accounts.Person` field, JSON-safe
(datetime → ISO-8601), `RES_ID` + `id` on the record and on every nested
sub-object (agency, country, emails, phones). Upsert semantics in the Flow
are keyed on `RES_ID`.

Covers the legacy `ZohoContactPostData` minimum checklist
(`legacy/workflows/11-integrations/zoho-crm.md`: id, RES_ID, Email,
First_Name, Last_Name, Full_Name, Phone, Title, Mobile, Address_Line_1)
mapped onto current model fields — there is no `accounts.Contact` model.

`notes` and `tags` push in full (user decision 2026-07-23): the
`SENSITIVE_TAGS` denylist below starts EMPTY — everything is included until
the business decides otherwise. Add `accounts.enums.PersonTag` values to the
frozenset to withhold specific tags from the CRM.

`relationships` carries both legs of the GAP-041 person graph (2026-07-24):
`kind`/`direction` are the raw stored fact, `relation` is the display label
from THIS person's perspective (inbound legs resolve through
`RELATIONSHIP_INVERSE_LABEL`, e.g. the PA row shows "Principal" on the other
side). Rows whose other party is ANONYMIZED are omitted — `Person.anonymize`
deletes relationship rows, so this guards the in-flight window.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from accounts.enums import RELATIONSHIP_INVERSE_LABEL, PhoneLabel
from accounts.models import Organisation, Person, PersonEmail, PersonPhone
from integrations.services.zoho_flow import is_anonymized_person

# Denylist of `accounts.enums.PersonTag` values withheld from the CRM.
# Deliberately empty for now — all tags (including the GAP-040
# special-category markers) push until the business asks to withhold any.
SENSITIVE_TAGS: frozenset[str] = frozenset()


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
        "notes": agency.notes,
        "status": agency.status,
    }


def _relationship_party(person: Person) -> dict[str, Any]:
    return {
        "RES_ID": person.pk,
        "id": person.pk,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "full_name": person.display_name or "",
    }


def _relationship_payloads(person: Person) -> list[dict[str, Any]]:
    """Both legs of the GAP-041 graph, from this person's perspective.

    A stored row reads "to_person is from_person's {kind}", so an inbound leg
    renders the other party under the inverse display label. Anonymized other
    parties are skipped entirely (their linkage must not leak to the CRM).
    """
    rows: list[dict[str, Any]] = []
    legs = (
        ("out", person.relationships_out.select_related("to_person"), "to_person"),
        ("in", person.relationships_in.select_related("from_person"), "from_person"),
    )
    for direction, queryset, other_field in legs:
        for rel in queryset:
            other = getattr(rel, other_field)
            if is_anonymized_person(other):
                continue
            relation = (
                rel.get_kind_display()
                if direction == "out"
                else RELATIONSHIP_INVERSE_LABEL[rel.kind]
            )
            rows.append(
                {
                    "RES_ID": rel.pk,
                    "id": rel.pk,
                    "kind": rel.kind,
                    "direction": direction,
                    "relation": relation,
                    "note": rel.note,
                    "person": _relationship_party(other),
                }
            )
    return rows


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
        "notes": person.notes,
        "status": person.status,
        "kind": person.kind,
        "primary_email": person.primary_email(),
        "primary_phone": person.primary_phone(),
        "mobile": mobiles[0] if mobiles else None,
        "emails": [_email_payload(e) for e in emails],
        "phones": [_phone_payload(p) for p in phones],
        "relationships": _relationship_payloads(person),
        "created_at": _iso(person.created_at),
        "updated_at": _iso(person.updated_at),
    }
