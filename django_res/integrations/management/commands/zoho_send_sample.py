"""`zoho_send_sample` — push one maximally-populated sample of each kind.

Ops utility for exercising the GAP-081/082 payload contracts against real
Zoho Flow webhooks before the backfill: picks the richest contact / villa /
enquiry / quote / booking (every FK and collection the payload builders
traverse populated) and pushes each through the SAME production pipeline as
live traffic — `ensure_pending_record` + a synchronous `push_sync_record`
call — so no Celery worker is needed and `SyncRecord` state updates
identically.

Contacts go first (including the villa's assigned persons and the enquiry's /
quote's / booking's own person and agent), then villas (the picked one plus
the enquiry's / quote-lines' / booking's own properties), then enquiry /
quote / booking, so every RES_ID nested in the downstream payloads resolves
to a record the CRM side has already received. The booking's own quotation
pushes as the quote kind only when sent/accepted with a real line — a
deliberately conservative subset of the backfill's eligibility (which also
counts expired/cancelled quotes carrying a QUOTE_SENT marker); a booking
sampled off a quotation outside that subset nests a quote RES_ID this run
leaves unresolved (`is_synthetic` flags only the legacy `booking-*` case).

Selection degrades gracefully: richness requirements are applied greedily in
priority order, keeping each only if some row still satisfies it alongside
those already kept — whatever was relaxed is reported, as are optional
scalar fields that ended up empty, so the output always states what the
sample does NOT demonstrate. Idempotent: re-running re-upserts the same
RES_IDs.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from django.core.management.base import BaseCommand
from django.db import models
from django.db.models import Count, QuerySet

from accounts.enums import PersonStatus, PhoneLabel
from accounts.models import Person
from integrations.services.zoho_flow import (
    ZOHO_FLOW_KINDS,
    ensure_pending_record,
    registered_zoho_models,
    webhook_url,
)
from integrations.tasks import push_sync_record

# Bound the richness scan — sampling, not a sweep (that's `zoho_backfill`).
CANDIDATE_LIMIT = 100

M = TypeVar("M", bound=models.Model)

# (name, queryset transform) — name is what gets reported when relaxed.
Requirement = tuple[str, Callable[[QuerySet[Any]], QuerySet[Any]]]


def _blank(value: Any) -> bool:
    return value in (None, "", [])


class Command(BaseCommand):
    help = (
        "Pick the richest contact/villa/enquiry/quote/booking (all payload "
        "FKs and collections populated, relaxing requirements if the data "
        "can't satisfy them) and push each synchronously to the Zoho Flow "
        "webhooks."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Pick and report the samples without pushing anything.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write(
            "webhook URLs configured: "
            + ", ".join(f"{k}={bool(webhook_url(k))}" for k in ZOHO_FLOW_KINDS)
        )

        # The import spine forbids integrations → reservations, so the
        # enquiry/quote models come from the push registry (populated by
        # `reservations.apps` at startup) — same as `zoho_backfill`.
        models_by_kind = {spec.kind: model for model, spec in registered_zoho_models().items()}

        person = self._pick_person()
        villa = self._pick_villa(models_by_kind.get("villa"))
        enquiry = self._pick_enquiry(models_by_kind.get("enquiry"))
        quotation = self._pick_quotation(models_by_kind.get("quote"))
        booking = self._pick_booking(models_by_kind.get("booking"))

        if options["dry_run"]:
            self.stdout.write("dry run — nothing pushed")
            return

        booking_quotation = booking.quotation_line.quotation if booking else None
        booking_enquiry = booking_quotation.enquiry if booking_quotation else None
        # Quote-kind eligibility for the booking's own quotation (see module
        # docstring): drafts and synthetic fill rows never push as quotes.
        eligible_booking_quotation = (
            booking_quotation
            if booking_quotation is not None
            and booking_quotation.status in ("sent", "accepted")
            and booking_quotation.lines.real().exists()
            else None
        )

        # Contacts first, then villas, so the RES_IDs nested inside the
        # downstream payloads already exist Zoho-side.
        villa_persons = (
            [
                a.contact
                for a in villa.contact_assignments.all()
                if a.contact is not None and a.contact.status != PersonStatus.ANONYMIZED
            ]
            if villa
            else []
        )
        contacts = {
            p.pk: p
            for p in (
                person,
                *villa_persons,
                enquiry.person if enquiry else None,
                enquiry.agent if enquiry else None,
                quotation.person if quotation else None,
                quotation.agent if quotation else None,
                quotation.enquiry.person if quotation and quotation.enquiry else None,
                quotation.enquiry.agent if quotation and quotation.enquiry else None,
                booking.person if booking else None,
                booking.agent if booking else None,
                booking_enquiry.person if booking_enquiry else None,
                booking_enquiry.agent if booking_enquiry else None,
                # The eligible booking-quotation's own agent can differ from
                # the booking's agent (it's a create-time parameter).
                eligible_booking_quotation.agent if eligible_booking_quotation else None,
            )
            if p is not None and p.status != PersonStatus.ANONYMIZED
        }
        for contact in contacts.values():
            self._send(contact, "contact")
        # The enquiry/quote/booking payloads nest their own properties'
        # RES_IDs — push those as villas too, not just the independently-
        # picked richest one.
        quote_line_properties = (
            [line.property for line in quotation.lines.real()] if quotation else []
        )
        booking_quote_line_properties = (
            [line.property for line in eligible_booking_quotation.lines.real()]
            if eligible_booking_quotation
            else []
        )
        villas = {
            v.pk: v
            for v in (
                villa,
                enquiry.property if enquiry else None,
                *quote_line_properties,
                booking.property if booking else None,
                booking.quotation_line.property if booking else None,
                *booking_quote_line_properties,
            )
            if v is not None
        }
        for villa_obj in villas.values():
            self._send(villa_obj, "villa")
        enquiries = {
            e.pk: e
            for e in (
                enquiry,
                quotation.enquiry if quotation else None,
                booking_enquiry,
            )
            if e is not None
        }
        for enquiry_obj in enquiries.values() if enquiries else [None]:
            self._send(enquiry_obj, "enquiry")
        quotations = {q.pk: q for q in (quotation,) if q is not None}
        if eligible_booking_quotation is not None:
            quotations.setdefault(eligible_booking_quotation.pk, eligible_booking_quotation)
        for quotation_obj in quotations.values() if quotations else [None]:
            self._send(quotation_obj, "quote")
        self._send(booking, "booking")

    # ── pickers ──────────────────────────────────────────────────────────

    def _candidates(
        self,
        base: QuerySet[M],
        requirements: Sequence[Requirement],
        post_filter: Callable[[M], bool] | None = None,
    ) -> tuple[list[M], list[str]]:
        """Rows matching `base` + as many `requirements` as the data allows.

        Greedy, in priority order: each requirement is kept only if some row
        still satisfies it together with everything already kept, so one
        unsatisfiable requirement never costs the others. Returns
        (candidates, names-of-dropped-requirements)."""
        qs = base
        dropped: list[str] = []
        for name, apply in requirements:
            trial = apply(qs)
            if trial.exists():
                qs = trial
            else:
                dropped.append(name)
        found = list(qs.distinct()[:CANDIDATE_LIMIT])
        if post_filter is not None:
            found = [obj for obj in found if post_filter(obj)]
        return found, dropped

    def _pick(
        self,
        label: str,
        candidates: Sequence[M],
        dropped: list[str],
        optional_scalars: list[str],
    ) -> M | None:
        """Best candidate = fewest empty optional scalars."""
        best: M | None = None
        best_missing: list[str] = []
        for obj in candidates:
            missing = [f for f in optional_scalars if _blank(getattr(obj, f))]
            if best is None or len(missing) < len(best_missing):
                best, best_missing = obj, missing
            if not missing:
                break
        if best is None:
            self.stdout.write(f"[{label}] NO candidate found at all")
            return None
        if dropped:
            self.stdout.write(f"[{label}] relaxed requirements (unsatisfiable here): {dropped}")
        self.stdout.write(
            f"[{label}] picked pk={best.pk} — {best}; "
            f"empty optional fields: {best_missing or 'none'}"
        )
        return best

    def _pick_person(self) -> Person | None:
        base = Person.objects.exclude(status=PersonStatus.ANONYMIZED).select_related(
            "agency__country", "country"
        )
        requirements: list[Requirement] = [
            (
                "has_email",
                lambda qs: qs.annotate(n_emails=Count("emails", distinct=True)).filter(
                    n_emails__gt=0
                ),
            ),
            (
                "has_phone",
                lambda qs: qs.annotate(n_phones=Count("phones", distinct=True)).filter(
                    n_phones__gt=0
                ),
            ),
            ("agency", lambda qs: qs.filter(agency__isnull=False)),
            ("country", lambda qs: qs.filter(country__isnull=False)),
            ("tags", lambda qs: qs.exclude(tags=[])),
            ("notes", lambda qs: qs.exclude(notes="")),
            ("agency_country", lambda qs: qs.filter(agency__country__isnull=False)),
            ("agency_notes", lambda qs: qs.exclude(agency__notes="")),
            ("mobile_phone", lambda qs: qs.filter(phones__label=PhoneLabel.MOBILE)),
            (
                "relationships",
                lambda qs: qs.annotate(
                    n_rels=Count("relationships_out", distinct=True)
                    + Count("relationships_in", distinct=True)
                ).filter(n_rels__gt=0),
            ),
        ]
        candidates, dropped = self._candidates(base, requirements)
        return self._pick(
            "contact",
            candidates,
            dropped,
            ["title", "address_line_1", "town", "post_code", "website_url", "legacy_id"],
        )

    def _pick_villa(self, model: type[models.Model] | None) -> Any:
        if model is None:
            self.stdout.write("[villa] no registered model — skipped")
            return None
        from accounts.enums import ContactRole

        base = model._default_manager.select_related(
            "category", "region__country", "location__country", "capacity"
        ).prefetch_related("contact_assignments__contact", "rooms__beds")
        requirements: list[Requirement] = [
            ("location", lambda qs: qs.filter(location__isnull=False)),
            ("capacity", lambda qs: qs.filter(capacity__isnull=False)),
            (
                "rooms",
                lambda qs: qs.annotate(n_rooms=Count("rooms", distinct=True)).filter(n_rooms__gt=0),
            ),
            (
                "features",
                lambda qs: qs.annotate(n_features=Count("feature_links", distinct=True)).filter(
                    n_features__gt=0
                ),
            ),
            (
                "owner_person",
                lambda qs: qs.filter(
                    contact_assignments__role=ContactRole.OWNER,
                    contact_assignments__contact__isnull=False,
                ),
            ),
            (
                "management_org",
                lambda qs: qs.filter(
                    contact_assignments__role=ContactRole.MANAGEMENT_COMPANY,
                    contact_assignments__organisation__isnull=False,
                ),
            ),
            (
                "images",
                lambda qs: qs.annotate(n_images=Count("images", distinct=True)).filter(
                    n_images__gt=0
                ),
            ),
            ("room_beds", lambda qs: qs.filter(rooms__beds__isnull=False)),
            (
                "room_attributes",
                lambda qs: qs.filter(rooms__attribute_links__isnull=False),
            ),
            ("coordinates", lambda qs: qs.filter(location__latitude__isnull=False)),
        ]
        candidates, dropped = self._candidates(base, requirements)
        return self._pick(
            "villa",
            candidates,
            dropped,
            ["licence_number", "video_url", "legacy_id"],
        )

    def _pick_enquiry(self, model: type[models.Model] | None) -> Any:
        if model is None:
            self.stdout.write("[enquiry] no registered model — skipped")
            return None
        base = model._default_manager.exclude(
            person__status=PersonStatus.ANONYMIZED
        ).select_related(
            "person__agency",
            "agent",
            "assigned_to",
            "property__region__country",
            "region__country",
        )
        requirements: list[Requirement] = [
            ("person", lambda qs: qs.filter(person__isnull=False)),
            ("dates", lambda qs: qs.filter(date_from__isnull=False, date_to__isnull=False)),
            ("property", lambda qs: qs.filter(property__isnull=False)),
            ("agent", lambda qs: qs.filter(agent__isnull=False)),
            ("assigned_to", lambda qs: qs.filter(assigned_to__isnull=False)),
            ("region", lambda qs: qs.filter(region__isnull=False)),
            ("property_region", lambda qs: qs.filter(property__region__isnull=False)),
            ("person_agency", lambda qs: qs.filter(person__agency__isnull=False)),
            (
                "notes",
                lambda qs: qs.annotate(n_notes=Count("notes_collection", distinct=True)).filter(
                    n_notes__gt=0
                ),
            ),
        ]
        candidates, dropped = self._candidates(base, requirements)
        return self._pick(
            "enquiry",
            candidates,
            dropped,
            ["first_name", "email", "phone", "inbound_message", "referral_code", "site_source"],
        )

    def _pick_quotation(self, model: type[models.Model] | None) -> Any:
        if model is None:
            self.stdout.write("[quote] no registered model — skipped")
            return None
        # Sent-status + a real (non-synthesised) line are production quote
        # eligibility (matches `zoho_backfill`) — never relaxed. Status
        # literals are duck-typed strings (frozen TextChoices pinned by the
        # reservations suite), same as the backfill's eligibility query.
        base = (
            model._default_manager.filter(status__in=("sent", "accepted"))
            .exclude(person__status=PersonStatus.ANONYMIZED)
            .select_related("person__agency", "agent", "enquiry", "terms_version")
        )
        requirements: list[Requirement] = [
            ("enquiry", lambda qs: qs.filter(enquiry__isnull=False)),
            ("agent", lambda qs: qs.filter(agent__isnull=False)),
            ("expires_at", lambda qs: qs.filter(expires_at__isnull=False)),
            ("person_agency", lambda qs: qs.filter(person__agency__isnull=False)),
            ("line_property_region", lambda qs: qs.filter(lines__property__region__isnull=False)),
        ]

        def has_real_line(quotation: Any) -> bool:
            return bool(quotation.lines.real().exists())

        candidates, dropped = self._candidates(base, requirements, post_filter=has_real_line)
        return self._pick("quote", candidates, dropped, ["number", "legacy_id"])

    def _pick_booking(self, model: type[models.Model] | None) -> Any:
        if model is None:
            self.stdout.write("[booking] no registered model — skipped")
            return None
        # No terminal-failure statuses (never relaxed — a cancelled/expired/
        # declined row is a poor first sample of the contract). Status/prefix
        # literals are duck-typed strings, same as the quote picker.
        base = (
            model._default_manager.exclude(person__status=PersonStatus.ANONYMIZED)
            .exclude(status__in=("cancelled", "expired", "declined"))
            .select_related(
                "person__agency",
                "agent",
                "assigned_to",
                "property__region__country",
                "quotation_line__quotation__enquiry",
                "currency",
                "terms_version",
            )
        )
        requirements: list[Requirement] = [
            # A real (non-booking-synthesised) quotation, so the nested quote
            # RES_ID can resolve against a pushed quote record.
            (
                "real_quote",
                lambda qs: qs.exclude(quotation_line__quotation__legacy_id__startswith="booking-"),
            ),
            (
                "sent_quote",
                lambda qs: qs.filter(quotation_line__quotation__status__in=("sent", "accepted")),
            ),
            ("agent", lambda qs: qs.filter(agent__isnull=False)),
            ("assigned_to", lambda qs: qs.filter(assigned_to__isnull=False)),
            ("property_region", lambda qs: qs.filter(property__region__isnull=False)),
        ]
        candidates, dropped = self._candidates(base, requirements)
        return self._pick("booking", candidates, dropped, ["legacy_id"])

    # ── delivery ─────────────────────────────────────────────────────────

    def _send(self, obj: models.Model | None, kind: str) -> None:
        if obj is None:
            self.stdout.write(f"[{kind}] nothing to send")
            return
        if not webhook_url(kind):
            self.stdout.write(f"[{kind}] webhook URL unset — skipped")
            return
        record, _ = ensure_pending_record(obj)
        try:
            # Direct call (not .delay): synchronous, exact prod delivery
            # logic; a transport/5xx failure raises instead of autoretrying.
            push_sync_record(record.pk)
        except Exception as exc:  # report and continue to the next kind
            self.stdout.write(f"[{kind}] pk={obj.pk} transport/5xx failure: {exc!r}")
        record.refresh_from_db()
        suffix = f" ({record.error_message})" if record.error_message else ""
        self.stdout.write(f"[{kind}] pk={obj.pk} -> {record.status}{suffix}")
