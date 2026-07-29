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

`build_booking_payload` (GAP-082 Unit 6) is a single upsert keyed on the res
booking pk (`RES_ID`), no delete push by agreement — purpose is
reporting/segmentation, never recalculation. Contact/agent by RES_ID
(`_person_summary`, anonymized fails closed to None), villa by RES_ID via
`property`, quote + enquiry links, and `line` = the accepted QuotationLine in
the EXACT quote-line shape (`_line_payload`) so the Flow mapping shares one
line schema with the quote kind. `quote.is_synthetic` flags
booking-synthesised legacy quotations (`legacy_id` `booking-*`) — those never
push as the quote kind, so the flag prevents dangling Flow joins.
`booking_date` = `created_at` (the historic-import filter; the loader
back-stamps it from legacy `CreatedAt`). `financials` (GAP-085, contract
pinned on the 2026-07-29 Limitless call) carries every owner-money figure
explicitly — Zoho-side formula fields cannot reproduce our non-proportional
commission (GAP-076 pass-through extras, GAP-077 residual-on-BALANCE), so
nothing is left for Zoho to derive. Figures come from the FinanceTab
authority (`owner_finance`), 2dp strings; keys are always present and
degrade to null (sparse imported snapshot / no schedule rows) — never
invented zeros. An authority 0.00 (e.g. a booking cancelled while its
schedule was still PENDING) is pushed as-is. `extras` itemizes the
engine-applied pricing extras plus manual charge lines with their
commissionable flags — informational only (both already sit inside
`total_gross`); `category` stays null until the GAP-088 taxonomy.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from integrations.services.zoho_flow import is_anonymized_person

if TYPE_CHECKING:
    from accounts.models import Person
    from properties.models.geo import Region
    from properties.models.property import Property
    from reservations.models import Booking, Enquiry, Quotation
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


_FINANCIALS_KEYS = (
    "total_gross",
    "total_net",
    "gross_deposit",
    "net_deposit",
    "deposit_commission",
    "gross_balance",
    "net_balance",
    "balance_commission",
)


def _financials_payload(booking: Booking) -> dict[str, Any]:
    """GAP-085: the 8-figure owner-money block, every figure explicit.

    Source of truth = `owner_finance` (the FinanceTab authority), so res-UI
    and Zoho can never disagree. Keys always present; a figure the authority
    can't produce is null (sparse imported snapshot → all null; owner money
    but no deposit/balance schedule rows → component figures null), never an
    invented zero.
    """
    from reservations.services.owner_finance import (
        owner_money_for_booking,
        payment_component_splits,
    )

    money = owner_money_for_booking(booking)
    if money is None:
        return dict.fromkeys(_FINANCIALS_KEYS)
    # ≤1 component per purpose: `payment_component_splits`' aggregation loop
    # emits one summed component per purpose, so this keyed collapse is
    # lossless and the per-purpose figures ARE the FinanceTab row figures.
    splits = {s["purpose"]: s for s in payment_component_splits(booking, money=money) or []}

    def _component(purpose: str, field: str) -> str | None:
        split = splits.get(purpose)
        return f"{split[field]:.2f}" if split is not None else None  # type: ignore[literal-required]

    return {
        "total_gross": f"{money['gross_total']:.2f}",
        "total_net": f"{money['net_to_owner']:.2f}",
        "gross_deposit": _component("deposit", "gross"),
        "net_deposit": _component("deposit", "net_to_owner"),
        "deposit_commission": _component("deposit", "commission"),
        "gross_balance": _component("balance", "gross"),
        "net_balance": _component("balance", "net_to_owner"),
        "balance_commission": _component("balance", "commission"),
    }


def _extras_payload(booking: Booking) -> list[dict[str, Any]]:
    """GAP-085: itemized extras with commissionable flags, per the call.

    Engine-applied pricing extras (snapshot `extras` — absent on imported
    snapshots) then manual charge lines, one shared entry shape. Purely
    informational: both sources already sit inside the financials
    `total_gross` (snapshot total / charge overlay) — Zoho must not re-add
    them. `category` is explicitly null until the GAP-088 taxonomy lands;
    key presence pins the contract, we do not fake a taxonomy.
    """
    snapshot = booking.pricing_snapshot or {}
    entries = [
        {
            "label": extra.get("name"),
            # Degrade-to-null, not the string "None" — the engine writes
            # str(Decimal), but future manual-override snapshot writes are
            # unfenced (reservations/views/quotation.py).
            "amount": (
                str(extra["computed_amount"]) if extra.get("computed_amount") is not None else None
            ),
            "commissionable": extra.get("commissionable"),
            "category": None,
        }
        for extra in snapshot.get("extras") or []
    ]
    entries.extend(
        {
            # Signed amounts verbatim — a negative line is a credit.
            "label": item.label,
            "amount": str(item.amount),
            "commissionable": item.commissionable,
            "category": None,
        }
        for item in booking.charge_items.all()
    )
    return entries


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


def build_booking_payload(booking: Booking) -> dict[str, Any]:
    """Full-field JSON-safe payload for one `reservations.Booking`.

    Built at push time from the live row (see
    `integrations.tasks.push_sync_record`) — the delivery task hands over a
    bare instance, so re-read it here with the full select_related chain
    rather than walking a dozen FKs lazily.
    """
    from reservations.models import Booking
    from reservations.models.quotation import SYNTHETIC_LEGACY_PREFIX
    from reservations.services.charges import with_charges_total

    booking = (
        # `with_charges_total` + `property__finance`: the financials block's
        # charge overlay reads the annotations (the un-annotated fallback
        # aggregates per call and bypasses prefetch).
        with_charges_total(Booking.objects.all())
        .select_related(
            "person__agency",
            "agent__agency",
            "assigned_to",
            "property__region__country",
            "property__finance",
            "currency",
            "terms_version",
            "quotation_line__quotation__enquiry",
            "quotation_line__property__region__country",
            "quotation_line__currency",
        )
        # primary_email()/primary_phone() iterate the prefetched collections;
        # the splits walk filters `payments` in Python; `charge_items` feeds
        # the extras itemization (the money path reads the annotations).
        .prefetch_related(
            "person__emails",
            "person__phones",
            "agent__emails",
            "agent__phones",
            "payments",
            "charge_items",
        )
        .get(pk=booking.pk)
    )
    line = booking.quotation_line
    quotation = line.quotation
    enquiry = quotation.enquiry
    return {
        "RES_ID": booking.pk,
        "id": booking.pk,
        "reference": booking.reference,
        "legacy_id": booking.legacy_id,
        "status": booking.status,
        "person": _person_summary(booking.person),
        "agent": _person_summary(booking.agent),
        "assigned_to": _assigned_to_payload(booking.assigned_to),
        "property": _property_payload(booking.property),
        "quote": {
            "RES_ID": quotation.pk,
            "id": quotation.pk,
            "reference": quotation.reference,
            "number": quotation.number,
            "legacy_id": quotation.legacy_id,
            # Booking-synthesised quotations never push as the quote kind —
            # the flag stops Flow joining a dangling quote RES_ID.
            "is_synthetic": (quotation.legacy_id or "").startswith(SYNTHETIC_LEGACY_PREFIX),
        },
        "enquiry": (
            {"RES_ID": enquiry.pk, "id": enquiry.pk, "reference": enquiry.reference}
            if enquiry is not None
            else None
        ),
        # EXACT quote-line shape — the Flow mapping shares one line schema.
        "line": _line_payload(line),
        # The booking's own dates/party — may drift from the line via
        # modify_dates / modify_guests.
        "date_from": _iso(booking.date_from),
        "date_to": _iso(booking.date_to),
        "nights": (booking.date_to - booking.date_from).days,
        "adults": booking.adults,
        "children": booking.children,
        "currency": booking.currency.code,
        "site_source": booking.site_source,
        "payment_method": booking.payment_method,
        "terms_version": {
            "RES_ID": booking.terms_version_id,
            "id": booking.terms_version_id,
            "version": booking.terms_version.version,
        },
        "terms_accepted_at": _iso(booking.terms_accepted_at),
        # Historic-import filter; the loader back-stamps created_at from the
        # legacy CreatedAt so this is faithful for imported rows.
        "booking_date": _iso(booking.created_at),
        "cancel_reason": booking.cancel_reason,
        "cancelled_at": _iso(booking.cancelled_at),
        "is_archived": booking.is_archived,
        "archived_at": _iso(booking.archived_at),
        "financials": _financials_payload(booking),
        "extras": _extras_payload(booking),
        "created_at": _iso(booking.created_at),
        "updated_at": _iso(booking.updated_at),
    }
