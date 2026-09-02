"""GAP-089: import Nick's "Enquiries" workbook (2017-2024 enquiry history).

One sheet, one pass, one transaction. Every row resolves to a `Person`
(`find_or_create_person`: e-mail + last name, tags unioned, agency from the
clean `Trade` column, phone filled in when the person has none, the loose
cells — `Linked`, `System Client Notes`, `Task notes`, unknown tags — appended
to `Person.notes` once). Then:

- a row **with** an `Enquiry Date` becomes a create-only `Enquiry`
  (`sheet-enquiry-…` key, explicit `E-SHEET-…` reference so the live sequence
  is untouched) in the historic DEAD / UNKNOWN / COLD state so 2,000+ old
  rows never surface in the live pipeline, with `created_at` back-stamped to
  the sheet date so history sorts truthfully;
- a row **without** one is a contact export, not an enquiry: the row's facts
  (source, villa, budget, notes) land on the Person as a notes line.

The res-DB `EnquiryLoader` covers Nov-2024 onward; this sheet covers before
that, so there is no cross-source dedupe (measured: no overlap). Runs under
`suppress_zoho_push()` (the Zoho backfill pushes the result later, on purpose)
with a savepoint per row; `--dry-run` rolls everything back after the report.

Usage::

    manage.py import_enquiry_sheet --file "Enquiries - FINAL.xlsx" [--dry-run]
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Organisation
from accounts.services.organisations import company_dedup_key, organisation_for_company_name
from accounts.services.person_channels import reconcile_primary_phone
from data_migration.loaders.sentinels import CLIENT_LEGACY_PREFIX, SHEET_LEGACY_PREFIX
from data_migration.sheets.matching import (
    PropertyMatcher,
    append_note_line,
    find_or_create_person,
    html_to_text,
    map_tags,
    parse_sheet_date,
    person_legacy_id,
    resolve_region,
)
from data_migration.sheets.report import SheetReport
from data_migration.sheets.xlsx import read_sheet
from integrations.services.zoho_flow import suppress_zoho_push
from reservations.enums import EnquiryLostReason, EnquirySource, EnquiryStatus, LeadStatus
from reservations.models import Enquiry
from reservations.phone import to_e164

SHEET = "Sheet1"

#: Historic rows have no outcome column; park them out of the live pipeline.
HISTORIC_STATUS = EnquiryStatus.DEAD
HISTORIC_LOST_REASON = EnquiryLostReason.UNKNOWN
HISTORIC_LEAD_STATUS = LeadStatus.COLD

#: `Source` values that are mailbox exports → `EMAIL_INBOUND`; the rest are
#: hand-kept lists (Nick, Trello, popop.csv, …) → `OTHER`.
EMAIL_SOURCE_PREFIXES = ("email_", "info mailbox")


def enquiry_legacy_key(email: str, enquiry_date: date, villa: str, first: str, last: str) -> str:
    return hashlib.sha1(
        f"{email.lower()}|{enquiry_date.isoformat()}|{villa.casefold()}"
        f"|{first.casefold()}|{last.casefold()}".encode()
    ).hexdigest()


def site_source_for(source: str) -> EnquirySource:
    if source.casefold().startswith(EMAIL_SOURCE_PREFIXES):
        return EnquirySource.EMAIL_INBOUND
    return EnquirySource.OTHER


def _text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    return str(value).strip() if value is not None else ""


def _budget(row: dict[str, Any]) -> str:
    budget = _text(row, "Budget")
    return "" if budget.casefold() in ("", "none-none") else budget


def _channels_writable(legacy_id: str | None) -> bool:
    """Sheet- and client-keyed people (and hand-made ones) may gain a channel;
    a legacy owner/agent Person (bare VillaContact id) may not, or the
    PersonPhone reconcile count would drift from VillaContactTele."""
    return legacy_id is None or legacy_id.startswith((SHEET_LEGACY_PREFIX, CLIENT_LEGACY_PREFIX))


class Command(BaseCommand):
    help = "GAP-089: import the historic enquiry sheet (Person + DEAD Enquiry per dated row)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--file", required=True, help="Path to the .xlsx workbook.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the report, then roll the whole import back.",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        path = Path(opts["file"])
        if not path.is_file():
            raise CommandError(f"No such file: {path}")
        try:
            rows = read_sheet(path, SHEET)
        except KeyError as exc:
            raise CommandError(f"Workbook is missing a sheet: {exc}") from exc

        report = SheetReport("import_enquiry_sheet")
        report.rows_read = len(rows)
        with suppress_zoho_push(), transaction.atomic():
            matcher = PropertyMatcher()
            for index, row in enumerate(rows, start=2):
                try:
                    with transaction.atomic():
                        self._import_row(row, matcher, report)
                except Exception as exc:
                    report.errors.append((f"{SHEET}!{index}", repr(exc)))
            self.stdout.write(report.render())
            if opts["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write("[dry-run] rolled back — nothing written.")

    def _import_row(
        self, row: dict[str, Any], matcher: PropertyMatcher, report: SheetReport
    ) -> None:
        first, last, email = _text(row, "First Name"), _text(row, "Last Name"), _text(row, "Email")
        if not first and not last and not email:
            report.skipped["blank_row"] += 1
            return
        if email and "@" not in email:
            report.errors.append((f"{first} {last}".strip() or email, "invalid email"))
            return

        tags, unknown_tags = map_tags(row.get("Tags"))
        match = find_or_create_person(
            email=email or None,
            first_name=first,
            last_name=last,
            legacy_id=person_legacy_id(email, first, last),
        )
        person = match.person
        if match.inactive:
            # Minted or matched by an earlier run, since anonymised /
            # deactivated: leave it (and its enquiries) alone.
            report.skipped["person_inactive"] += 1
            return
        if match.created:
            report.created["person"] += 1
            if match.ambiguous:
                report.skipped["person_ambiguous_created_new"] += 1
        elif match.filled:
            report.updated["person"] += 1

        changed = False
        agency = self._agency(_text(row, "Trade"))
        if agency is not None and person.agency_id is None:
            person.agency = agency
            person.save(update_fields=["agency", "updated_at"])
            changed = True
        if tags and set(tags) - set(person.tags or []):
            person.tags = sorted({*(person.tags or []), *tags})
            person.save(update_fields=["tags", "updated_at"])
            changed = True
        phone = to_e164(_text(row, "Phone"))[:32]
        # Only people the sheets/clients own may gain a channel: a phone added
        # to a legacy owner/agent Person would drift `reconcile_legacy`'s
        # VillaContactTele count.
        if phone and not person.phones.exists() and _channels_writable(person.legacy_id):
            reconcile_primary_phone(person, phone)
            changed = True
        if unknown_tags:
            changed |= append_note_line(person, f"Sheet tags: {', '.join(unknown_tags)}")
        if _text(row, "Linked"):
            changed |= append_note_line(person, f"Linked to: {_text(row, 'Linked')}")
        for column in ("System Client Notes", "Task notes"):
            if _text(row, column):
                changed |= append_note_line(person, html_to_text(_text(row, column)))

        enquiry_date = parse_sheet_date(row.get("Enquiry Date"))
        if enquiry_date is None:
            changed |= append_note_line(person, self._undated_note(row))
            report.skipped["undated_row_person_only"] += 1
        else:
            self._import_enquiry(row, person, enquiry_date, matcher, report)
        if changed and not match.created:
            report.updated["person_notes_tags_phone"] += 1

    @staticmethod
    def _agency(trade: str) -> Organisation | None:
        """The `Trade` column's agency — get-or-create through the shared
        dedup key, and a `sheet-org-…` stamp on the ones this import mints so
        `reconcile_legacy` can leave them out of the VillaContact.Company
        comparison (an existing legacy org keeps its own id)."""
        if not trade:
            return None
        existed = Organisation.objects.filter(dedup_key=company_dedup_key(trade)).exists()
        org = organisation_for_company_name(trade)
        if org is not None and not existed:
            org.legacy_id = f"{SHEET_LEGACY_PREFIX}org-{(org.dedup_key or '')[:16]}"
            org.save(update_fields=["legacy_id"])
        return org

    @staticmethod
    def _undated_note(row: dict[str, Any]) -> str:
        parts = [f"Enquiry sheet (undated, source: {_text(row, 'Source') or 'unknown'})"]
        if _text(row, "Villa Enquired"):
            parts.append(f"villa: {_text(row, 'Villa Enquired')}")
        if _budget(row):
            parts.append(f"budget: {_budget(row)}")
        if _text(row, "Notes"):
            parts.append("notes: " + " / ".join(html_to_text(_text(row, "Notes")).splitlines()))
        return "; ".join(parts)

    def _import_enquiry(
        self,
        row: dict[str, Any],
        person: Any,
        enquiry_date: date,
        matcher: PropertyMatcher,
        report: SheetReport,
    ) -> None:
        first, last, email = _text(row, "First Name"), _text(row, "Last Name"), _text(row, "Email")
        villa = _text(row, "Villa Enquired")
        key = enquiry_legacy_key(email, enquiry_date, villa, first, last)
        prop = matcher.match(villa) if villa else None
        if villa and prop is None:
            report.unmatched_villas[villa] += 1

        header = [f"Source: {_text(row, 'Source')}"]
        if villa:
            header.insert(0, f"Villa enquired: {villa}")
        if _budget(row):
            header.append(f"Budget: {_budget(row)}")
        destination = " / ".join(p for p in (_text(row, "Region"), _text(row, "Country")) if p)
        if destination:
            header.append(f"Destination: {destination}")
        body = html_to_text(_text(row, "Notes"))
        message = "\n".join(header) + (f"\n\n{body}" if body else "")

        enquiry, created = Enquiry.objects.get_or_create(
            legacy_id=f"sheet-enquiry-{key[:16]}",
            defaults={
                "reference": f"E-SHEET-{key[:8].upper()}",
                "person": person,
                "first_name": first[:128],
                "last_name": last[:128],
                "email": email,
                "phone": to_e164(_text(row, "Phone"))[:32],
                "property": prop,
                "region": resolve_region(
                    _text(row, "Country") or None, _text(row, "Region") or None
                ),
                "site_source": site_source_for(_text(row, "Source")),
                "status": HISTORIC_STATUS,
                "lost_reason": HISTORIC_LOST_REASON,
                "lead_status": HISTORIC_LEAD_STATUS,
                "inbound_message": message,
            },
        )
        if not created:
            report.skipped["exists"] += 1
            return
        # Back-stamp `created_at` (auto_now_add ignores an explicit value) so the
        # enquiry sorts by its real date; the same technique as BookingLoader.
        stamp = timezone.make_aware(datetime.combine(enquiry_date, time.min))
        Enquiry.objects.filter(pk=enquiry.pk).update(created_at=stamp)
        report.created["enquiry"] += 1
