"""GAP-089: import Nick's "VC Past Bookers" workbook.

Two sheets, two passes, one transaction:

1. **Contacts** — one row per past booker (a Zoho-style contact export:
   prefix, name, e-mail, mailing address, free-text notes, an "Agent / Advisor"
   cell that is sometimes an agency and sometimes a commission note). Each row
   resolves to a `Person` via `find_or_create_person` (e-mail + last name;
   spouses sharing an address become two people). Matched people are only
   *filled in*; the notes cells are appended once.
2. **Booking History** — one row per historic stay: name, `BN123`, villa,
   destination, year. No dates or money, so each becomes a `PastStay`
   (create-only on its `sheet-stay-…` key), linked to the person by name
   (the in-run map from pass 1, else exactly one ACTIVE customer in the DB)
   and to a `Property` only when the villa name resolves unambiguously.

Everything runs under `suppress_zoho_push()` (the Zoho backfill pushes the
resulting people later, on purpose) inside one `transaction.atomic()` with a
savepoint per row, so one bad row is reported, not fatal. `--dry-run` rolls
the whole transaction back after printing the report. Re-runs are safe:
people are found by their `legacy_id`, stays by theirs.

Usage::

    manage.py import_past_bookers --file "VC Past Bookers Final.xlsx" [--dry-run]
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Person
from data_migration.sheets.matching import (
    PropertyMatcher,
    append_note_line,
    find_or_create_person,
    match_person_by_name,
    normalise_name,
    person_legacy_id,
    resolve_country,
)
from data_migration.sheets.report import SheetReport
from data_migration.sheets.xlsx import read_sheet
from integrations.services.zoho_flow import suppress_zoho_push
from reservations.models import PastStay

CONTACTS_SHEET = "Contacts"
HISTORY_SHEET = "Booking History"

#: A sentinel for "this name maps to more than one person in the sheet".
_AMBIGUOUS = None


def stay_legacy_id(first: str, last: str, booking_number: str, villa: str, year: int | None) -> str:
    digest = hashlib.sha1(
        f"{normalise_name(first)}|{normalise_name(last)}|{booking_number.casefold()}"
        f"|{normalise_name(villa)}|{year or ''}".encode()
    ).hexdigest()
    return f"sheet-stay-{digest[:16]}"


def _text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    return str(value).strip() if value is not None else ""


def parse_year(raw: str) -> int | None:
    try:
        year = int(float(raw))
    except (TypeError, ValueError):
        return None
    return year if 1990 <= year <= 2100 else None


class Command(BaseCommand):
    help = "GAP-089: import past bookers (Contacts → Person, Booking History → PastStay)."

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
            contacts = read_sheet(path, CONTACTS_SHEET)
            history = read_sheet(path, HISTORY_SHEET)
        except KeyError as exc:
            raise CommandError(f"Workbook is missing a sheet: {exc}") from exc

        report = SheetReport("import_past_bookers")
        report.rows_read = len(contacts) + len(history)
        with suppress_zoho_push(), transaction.atomic():
            by_name = self._import_contacts(contacts, report)
            self._import_history(history, by_name, report)
            self.stdout.write(report.render())
            if opts["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write("[dry-run] rolled back — nothing written.")

    # --- pass 1: Contacts -------------------------------------------------

    def _import_contacts(
        self, rows: list[dict[str, Any]], report: SheetReport
    ) -> dict[tuple[str, str], Person | None]:
        by_name: dict[tuple[str, str], Person | None] = {}
        for index, row in enumerate(rows, start=2):
            counts = report.row_counts()
            try:
                with transaction.atomic():
                    person = self._import_contact(row, report)
            except Exception as exc:
                report.restore_row_counts(counts)  # the row rolled back (BUG-030 §34)
                report.errors.append((f"{CONTACTS_SHEET}!{index}", repr(exc)))
                continue
            if person is None:
                continue
            key = (normalise_name(row.get("First Name")), normalise_name(row.get("Last Name")))
            if key in by_name and by_name[key] != person:
                by_name[key] = _AMBIGUOUS
            else:
                by_name.setdefault(key, person)
        return by_name

    def _import_contact(self, row: dict[str, Any], report: SheetReport) -> Person | None:
        first, last, email = _text(row, "First Name"), _text(row, "Last Name"), _text(row, "Email")
        if not first and not last and not email:
            report.skipped["blank_row"] += 1
            return None
        if email and "@" not in email:
            report.skipped["invalid_email"] += 1
            email = ""
        mailing_country = _text(row, "Mailing Country")
        country = resolve_country(mailing_country)
        if mailing_country and country is None:
            report.skipped["country_unresolved"] += 1
        match = find_or_create_person(
            email=email or None,
            first_name=first,
            last_name=last,
            legacy_id=person_legacy_id(email, first, last),
            defaults={
                "title": _text(row, "Prefix")[:16],
                "address_line_1": _text(row, "Mailing Street")[:255],
                "town": _text(row, "Mailing City")[:128],
                "post_code": _text(row, "Mailing Zip")[:32],
                "country": country,
            },
        )
        if match.inactive:
            # Minted by an earlier run, since anonymised/deactivated: leave it.
            report.skipped["person_inactive"] += 1
            return None
        if match.created:
            report.created["person"] += 1
            if match.ambiguous:
                report.skipped["person_ambiguous_created_new"] += 1
        elif match.filled:
            report.updated["person"] += 1

        changed = False
        notes = _text(row, "Notes notes")
        if notes:
            changed |= append_note_line(match.person, notes)
        advisor = _text(row, "Agent / Advisor")
        if advisor:
            changed |= append_note_line(match.person, f"Agent/advisor: {advisor}")
        if changed and not match.created:
            report.updated["person_notes"] += 1
        return match.person

    # --- pass 2: Booking History ------------------------------------------

    def _import_history(
        self,
        rows: list[dict[str, Any]],
        by_name: dict[tuple[str, str], Person | None],
        report: SheetReport,
    ) -> None:
        matcher = PropertyMatcher()
        seen: set[str] = set()
        for index, row in enumerate(rows, start=2):
            counts = report.row_counts()
            try:
                with transaction.atomic():
                    self._import_stay(row, by_name, matcher, report, seen)
            except Exception as exc:
                report.restore_row_counts(counts)  # the row rolled back (BUG-030 §34)
                report.errors.append((f"{HISTORY_SHEET}!{index}", repr(exc)))

    def _resolve_person(
        self, first: str, last: str, by_name: dict[tuple[str, str], Person | None]
    ) -> Person | None:
        key = (normalise_name(first), normalise_name(last))
        if key in by_name:
            return by_name[key]  # a Person, or the ambiguity sentinel
        person, _ambiguous = match_person_by_name(first, last)
        return person

    def _import_stay(
        self,
        row: dict[str, Any],
        by_name: dict[tuple[str, str], Person | None],
        matcher: PropertyMatcher,
        report: SheetReport,
        seen: set[str],
    ) -> None:
        first, last = _text(row, "First Name"), _text(row, "Last Name")
        raw_number, villa = _text(row, "Booking Number"), _text(row, "Villa Booked")
        if not first and not last and not raw_number and not villa:
            report.skipped["blank_row"] += 1
            return
        person = self._resolve_person(first, last, by_name)
        if person is None:
            report.skipped["person_unmatched"] += 1
            report.unmatched_persons[f"{first} {last}".strip()] += 1
            return

        number_lines = [line.strip() for line in raw_number.splitlines() if line.strip()]
        booking_number = (number_lines[0] if number_lines else "")[:32]
        note_lines = number_lines[1:]
        raw_year = _text(row, "Year of Check-In")
        year = parse_year(raw_year)
        if raw_year and year is None:
            report.skipped["bad_year"] += 1
            note_lines.append(f"Year as written: {raw_year}")
        prop = matcher.match(villa) if villa else None
        if villa and prop is None:
            report.unmatched_villas[villa] += 1

        legacy_id = stay_legacy_id(first, last, booking_number, villa, year)
        if legacy_id in seen:
            # Two rows in ONE run with the same key are a sheet duplicate (or a
            # same-villa-same-year repeat with no BN) — say so rather than
            # reporting the second as an idempotent re-hit.
            report.skipped["duplicate_row"] += 1
            return
        _, created = PastStay.objects.get_or_create(
            legacy_id=legacy_id,
            defaults={
                "person": person,
                "booking_number": booking_number,
                "villa_name": villa[:255],
                "property": prop,
                "destination": _text(row, "Destination")[:255],
                "year": year,
                "notes": "\n".join(note_lines),
            },
        )
        # Only once the write succeeded: a rolled-back row must not make an
        # identical later row look like a duplicate (BUG-030 §34).
        seen.add(legacy_id)
        if created:
            report.created["past_stay"] += 1
        else:
            report.skipped["exists"] += 1
