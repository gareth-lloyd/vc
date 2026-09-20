"""GAP-112: relink customer-less legacy enquiries to the people the sheet
imports minted after `loadlegacy` ran.

    manage.py relink_enquiry_customers [--dry-run] [--mint-unmatched]

Runs after `import_enquiry_sheet` and `import_past_bookers`, before
`reconcile_legacy` (CUTOVER §4). For each enquiry `EnquiryLoader` left without
a customer, `classify_enquiry` re-asks the loader's strict match; on a unique
hit the enquiry gets its person, every quotation of it still on the
unknown-client sentinel follows, and so does every sentinel guest preference
recorded against one of those quotations. Ambiguous and unresolvable rows are
reported per category, never guessed. Each write is a `.save()`, so the
AuditLog trail records every customer change. Idempotent: a second run finds
nothing to do.

GAP-118 §3 adds `--mint-unmatched`: for an address no loaded Person holds at
all (`unmatched` — 543 enquiries on the 2026-09-18 dev DB, 51 of them carrying
sentinel quotations), mint one customer Person per distinct address and link
every enquiry that carries it. **Opt-in, and only on the FINAL relink** — the
cutover runs this pass twice (CUTOVER §4), and minting on the first would
create people `import_archive_stays` is about to mint properly, exactly the
duplication GAP-112's "Why not in GAP-108" rejected. The ambiguous categories
(`shared_email`, `names_disagree`, `no_email`, `inactive`) are never minted.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.enums import PersonKind, PersonStatus
from accounts.models import Person
from accounts.services.person_channels import reconcile_primary_email, reconcile_primary_phone
from data_migration.loaders.sentinels import UNKNOWN_CLIENT_LEGACY_ID
from data_migration.relink import (
    ANON_FIRST_NAME,
    classify_enquiry,
    enquiry_person_legacy_id,
    unlinked_legacy_enquiries,
)
from data_migration.sheets.report import SheetReport
from integrations.services.zoho_flow import suppress_zoho_push
from reservations.models import Enquiry, GuestPreference, Quotation

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
        parser.add_argument(
            "--mint-unmatched",
            action="store_true",
            help=(
                "GAP-118: mint one customer Person per unmatched enquiry address. "
                "Only on the FINAL relink, after import_archive_stays."
            ),
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        report = SheetReport("relink_enquiry_customers")
        with suppress_zoho_push(), transaction.atomic():
            sentinel = Person.objects.filter(legacy_id=UNKNOWN_CLIENT_LEGACY_ID).first()
            relinked: set[int] = set()
            # Address -> the enquiries carrying it, in pk order (the queryset's).
            mintable: dict[str, list[Enquiry]] = defaultdict(list)
            for enquiry in unlinked_legacy_enquiries():
                report.rows_read += 1
                category, person = classify_enquiry(enquiry)
                if person is None:
                    if category == "unmatched" and opts["mint_unmatched"]:
                        mintable[(enquiry.email or "").strip().lower()].append(enquiry)
                        continue  # accounted for by the mint pass below
                    report.skipped[f"enquiry: {category}"] += 1
                    if sentinel is not None:
                        stranded = enquiry.quotations.filter(person=sentinel).count()
                        report.skipped[f"quotation: {category}"] += stranded
                    continue
                enquiry.person = person
                enquiry.save(update_fields=SAVE_FIELDS)
                relinked.add(enquiry.pk)
                report.updated["enquiry"] += 1
            # Before `_follow`, and joining `relinked`: `_follow`'s queryset
            # filters `enquiry__person__isnull=False` and is evaluated at call
            # time, so it picks up these links — but only if they exist first.
            # Minting after it would strand the quotations and turn the
            # `reconcile_legacy` invariant "Quotation on unknown client with a
            # relinkable enquiry (must be 0)" RED.
            self._mint(mintable, relinked, report)
            if sentinel is not None:
                self._follow(sentinel, relinked, report)
            self.stdout.write(report.render())
            if opts["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write("[dry-run] rolled back — nothing written.")

    def _mint(
        self, groups: dict[str, list[Enquiry]], relinked: set[int], report: SheetReport
    ) -> None:
        """One customer Person per unmatched address, then link its enquiries.

        Hand-rolled rather than `sheets.matching.find_or_create_person`: that
        helper keys on `sheet-person-<sha1(address|names)>`, not our prefix,
        and re-runs `match_person_by_email(active_only=False)`, which would
        attach to a deactivated holder the strict matcher deliberately refused.
        """
        for addr, enquiries in sorted(groups.items()):
            # No "does anybody hold this address?" re-check: `PersonEmail.email`
            # is a `CIEmailField` (lowercased on write, citext), so
            # `classify_enquiry`'s lookup is already case-insensitive — a
            # case-variant holder comes back `relinked`, never `unmatched`.
            named = next((e for e in enquiries if self._has_name(e)), enquiries[0])
            # `(anon)` is the loader's placeholder, so it is dropped per FIELD,
            # not just per row: `(anon) Smith` is a surname with no first name.
            first = "" if named.first_name == ANON_FIRST_NAME else named.first_name
            # A wholly anonymous group falls back to the address, exactly as
            # `find_or_create_person` does (`sheets/matching.py:424-426`): a
            # nameless Person renders as "Client #id" in the staff lists.
            fallback = "" if named.last_name else addr[:128]
            # The phone is picked independently of the name — the two need not
            # sit on the same enquiry, and a number dropped here is never
            # re-added (both sheet importers guard on `not phones.exists()`).
            phone = next((e.phone for e in enquiries if e.phone), "")
            person, created = Person.objects.get_or_create(
                legacy_id=enquiry_person_legacy_id(addr),
                defaults={
                    "kind": PersonKind.CUSTOMER,
                    "status": PersonStatus.ACTIVE,
                    "first_name": first or fallback,
                    "last_name": named.last_name,
                },
            )
            if created:
                report.created["person (minted from enquiry)"] += 1
            distinct = {(e.first_name, e.last_name) for e in enquiries if self._has_name(e)}
            if len(distinct) > 1:
                # The address IS the grouping (a second real holder would have
                # been `shared_email` and never reached here), so these merge —
                # but the name not taken must be visible, not silently lost.
                report.skipped["name not used (address carries several)"] += len(distinct) - 1
            reconcile_primary_email(person, addr)
            if phone:
                reconcile_primary_phone(person, phone[:32])
            for enquiry in enquiries:
                enquiry.person = person
                enquiry.save(update_fields=SAVE_FIELDS)
                relinked.add(enquiry.pk)
                report.updated["enquiry (minted customer)"] += 1

    @staticmethod
    def _has_name(enquiry: Enquiry) -> bool:
        """`EnquiryLoader` stores `(anon)` for a nameless row — not a name."""
        return bool(enquiry.last_name) or enquiry.first_name not in ("", ANON_FIRST_NAME)

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
