"""GAP-112: relink customer-less legacy enquiries to the people the sheet
imports minted after `loadlegacy` ran.

    manage.py relink_enquiry_customers [--dry-run]

Runs after `import_enquiry_sheet` and `import_past_bookers`, before
`reconcile_legacy` (CUTOVER §4). For each enquiry `EnquiryLoader` left without
a customer, `classify_enquiry` re-asks the loader's strict match; on a unique
hit the enquiry gets its person, every quotation of it still on the
unknown-client sentinel follows, and so does every sentinel guest preference
recorded against one of those quotations. Ambiguous and unresolvable rows are
reported per category, never guessed. Each write is a `.save()`, so the
AuditLog trail records every customer change. Idempotent: a second run finds
nothing to do.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Person
from data_migration.loaders.sentinels import UNKNOWN_CLIENT_LEGACY_ID
from data_migration.relink import classify_enquiry, unlinked_legacy_enquiries
from data_migration.sheets.report import SheetReport
from integrations.services.zoho_flow import suppress_zoho_push
from reservations.models import GuestPreference, Quotation

SAVE_FIELDS = ["person", "updated_at"]


class Command(BaseCommand):
    help = (
        "GAP-112: relink customer-less legacy enquiries, their sentinel quotations and preferences."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the report, then roll the whole pass back.",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        report = SheetReport("relink_enquiry_customers")
        with suppress_zoho_push(), transaction.atomic():
            sentinel = Person.objects.filter(legacy_id=UNKNOWN_CLIENT_LEGACY_ID).first()
            relinked: set[int] = set()
            for enquiry in unlinked_legacy_enquiries():
                report.rows_read += 1
                category, person = classify_enquiry(enquiry)
                if person is None:
                    report.skipped[f"enquiry: {category}"] += 1
                    if sentinel is not None:
                        stranded = enquiry.quotations.filter(person=sentinel).count()
                        report.skipped[f"quotation: {category}"] += stranded
                    continue
                enquiry.person = person
                enquiry.save(update_fields=SAVE_FIELDS)
                relinked.add(enquiry.pk)
                report.updated["enquiry"] += 1
            if sentinel is not None:
                self._follow(sentinel, relinked, report)
            self.stdout.write(report.render())
            if opts["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write("[dry-run] rolled back — nothing written.")

    def _follow(self, sentinel: Person, relinked: set[int], report: SheetReport) -> None:
        """Move sentinel quotations onto their (now) linked enquiry's person,
        then the sentinel preferences recorded against the quotations moved."""
        moved: dict[int, Person] = {}
        quotations = (
            Quotation.objects.filter(
                person=sentinel, legacy_id__isnull=False, enquiry__person__isnull=False
            )
            .exclude(enquiry__person=sentinel)
            .select_related("enquiry__person")
        )
        for quotation in quotations.order_by("pk"):
            person = quotation.enquiry.person
            assert person is not None  # filtered above
            quotation.person = person
            quotation.save(update_fields=SAVE_FIELDS)
            moved[quotation.pk] = person
            if quotation.enquiry_id in relinked:
                report.updated["quotation"] += 1
            else:
                # QuotationLoader back-filled the enquiry from a later quotation.
                report.updated["quotation (enquiry already linked)"] += 1
        preferences = GuestPreference.objects.filter(person=sentinel, quotation__in=moved)
        for preference in preferences.order_by("pk"):
            assert preference.quotation_id is not None  # filtered above
            person = moved[preference.quotation_id]
            if GuestPreference.objects.filter(
                person=person,
                preference_type_id=preference.preference_type_id,
                quotation_id=preference.quotation_id,
            ).exists():
                report.skipped["guest_preference: conflict"] += 1
                continue
            preference.person = person
            preference.save(update_fields=SAVE_FIELDS)
            report.updated["guest_preference"] += 1
