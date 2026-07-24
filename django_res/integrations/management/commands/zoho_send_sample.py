"""`zoho_send_sample` — push one maximally-populated sample of each kind.

Ops utility for exercising the GAP-081 payload contract against real Zoho
Flow webhooks before the backfill: picks the richest contact / enquiry /
quote (every FK and collection the payload builders traverse populated) and
pushes each through the SAME production pipeline as live traffic —
`ensure_pending_record` + a synchronous `push_sync_record` call — so no
Celery worker is needed and `SyncRecord` state updates identically.

Contacts go first, and the enquiry's / quote's own person and agent are
pushed too, so every RES_ID nested in the enquiry/quote payloads resolves to
a contact the CRM side has already received.

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
        "Pick the richest contact/enquiry/quote (all payload FKs and "
        "collections populated, relaxing requirements if the data can't "
        "satisfy them) and push each synchronously to the Zoho Flow webhooks."
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
            + ", ".join(f"{k}={bool(webhook_url(k))}" for k in ("contact", "enquiry", "quote"))
        )

        # The import spine forbids integrations → reservations, so the
        # enquiry/quote models come from the push registry (populated by
        # `reservations.apps` at startup) — same as `zoho_backfill`.
        models_by_kind = {spec.kind: model for model, spec in registered_zoho_models().items()}

        person = self._pick_person()
        enquiry = self._pick_enquiry(models_by_kind.get("enquiry"))
        quotation = self._pick_quotation(models_by_kind.get("quote"))

        if options["dry_run"]:
            self.stdout.write("dry run — nothing pushed")
            return

        # Contacts first so the RES_IDs nested inside the enquiry/quote
        # payloads already exist Zoho-side.
        contacts = {
            p.pk: p
            for p in (
                person,
                enquiry.person if enquiry else None,
                enquiry.agent if enquiry else None,
                quotation.person if quotation else None,
                quotation.agent if quotation else None,
            )
            if p is not None
        }
        for contact in contacts.values():
            self._send(contact, "contact")
        self._send(enquiry, "enquiry")
        self._send(quotation, "quote")

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
