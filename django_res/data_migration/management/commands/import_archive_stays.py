"""GAP-113: land legacy `VillaArchiveBookings` onto `PastStay`.

Runs after the two sheet imports and `relink_enquiry_customers`, before
`reconcile_legacy`. The rows are read, re-saves grouped and each stay
classified by `data_migration.archive_stays` (read-only); this command only
writes the two outcomes:

- **enrich** — blank-fill the matched sheet stay's dates, amount and currency
  and append the archive notes once. Never its `property` (a re-run would see
  different candidates) and never the sheet stay's person.
- **create** — a `PastStay` keyed `archive-stay-<Id>` on the address's single
  ACTIVE CUSTOMER, else on `find_or_create_person` with the archive address.
  An ambiguous name match is rolled back and skipped rather than minting a
  duplicate; the phone is added only to a person with none whose channels the
  sheets own (`channels_writable`).

Every other category is reported with the legacy ids behind it. One
`transaction.atomic()` with a savepoint per stay, under `suppress_zoho_push()`;
`--dry-run` rolls it all back. A second run writes nothing: created stays are
found by their key, enriched ones have nothing left to fill.

Usage::

    manage.py import_archive_stays [--dry-run]
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Person
from accounts.services.person_channels import reconcile_primary_phone
from data_migration.archive_stays import (
    ARCHIVE_ROWS_SQL,
    ArchiveStay,
    Classification,
    classify,
    group_rows,
    notes_pending,
)
from data_migration.legacy_db import legacy_cursor, rows_as_dicts
from data_migration.loaders._util import legacy_phone
from data_migration.sheets.matching import (
    channels_writable,
    find_or_create_person,
    person_legacy_id,
    resolve_country,
)
from data_migration.sheets.report import SheetReport
from integrations.services.zoho_flow import suppress_zoho_push
from pricing.models import Currency
from properties.models import Property
from reservations.models import PastStay


def fetch_archive_rows() -> list[dict[str, Any]]:
    with legacy_cursor() as cursor:
        cursor.execute(ARCHIVE_ROWS_SQL)
        return list(rows_as_dicts(cursor))


def _ids(stay: ArchiveStay) -> str:
    return "/".join(str(i) for i in stay.member_ids)


class _PersonSkipped(Exception):
    """Roll the stay's savepoint back and report `reason` as a skip."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _currency(stay: ArchiveStay) -> Currency | None:
    if stay.currency_legacy_id is None:
        return None
    currency = Currency.objects.filter(legacy_id=stay.currency_legacy_id).first()
    if currency is None:
        raise ValueError(f"unknown CurrencyId {stay.currency_legacy_id}")
    return currency


class Command(BaseCommand):
    help = "GAP-113: VillaArchiveBookings → dated PastStays (enrich sheet stays, create the rest)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the report, then roll the whole import back.",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        rows = fetch_archive_rows()
        report = SheetReport("import_archive_stays")
        report.rows_read = len(rows)
        with suppress_zoho_push(), transaction.atomic():
            grouped = group_rows(rows)
            for legacy_id in grouped.test_row_ids:
                report.skipped["test_row"] += 1
                report.add_id("test_row", str(legacy_id))
            for legacy_id, message in grouped.errors:
                report.errors.append((str(legacy_id), message))
            for result in classify(grouped.stays):
                # Facts about the stay, named whatever it ends as (skipped,
                # rolled back, or a re-run's `exists`).
                for flag, raised in (
                    ("dates_dropped", result.stay.dates_dropped),
                    ("duplicate_conflict", result.stay.duplicate_conflict),
                    ("property_differs", result.property_differs),
                ):
                    if raised:
                        report.add_id(flag, _ids(result.stay))
                counts = report.row_counts()
                try:
                    with transaction.atomic():
                        self._land(result, report)
                except _PersonSkipped as skip:
                    report.restore_row_counts(counts)
                    report.skipped[skip.reason] += 1
                    report.add_id(skip.reason, _ids(result.stay))
                except Exception as exc:
                    report.restore_row_counts(counts)  # the row rolled back (BUG-030 §34)
                    report.errors.append((_ids(result.stay), str(exc)))
            self.stdout.write(report.render())
            if opts["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write("[dry-run] rolled back — nothing written.")

    def _land(self, result: Classification, report: SheetReport) -> None:
        stay = result.stay
        if result.category == "enrich" and result.target is not None:
            self._enrich(stay, result.target, report)
        elif result.category == "create":
            self._create(stay, result.email_person, report)
        else:
            report.skipped[result.category] += 1
            report.add_id(result.category, _ids(stay))

    def _enrich(self, stay: ArchiveStay, target: PastStay, report: SheetReport) -> None:
        fields: list[str] = []
        if target.date_from is None and stay.date_from is not None:
            target.date_from, target.date_to = stay.date_from, stay.date_to
            fields += ["date_from", "date_to"]
        if target.amount is None and stay.amount is not None:
            target.amount = stay.amount
            fields.append("amount")
        if target.currency_id is None and stay.currency_legacy_id is not None:
            target.currency = _currency(stay)
            fields.append("currency")
        if notes_pending(stay, target):
            target.notes = f"{target.notes}\n{stay.notes}" if target.notes else stay.notes
            fields.append("notes")
        target.save(update_fields=[*fields, "updated_at"])
        report.updated["past_stay"] += 1

    def _create(self, stay: ArchiveStay, holder: Person | None, report: SheetReport) -> None:
        person = holder or self._find_or_create_person(stay, report)
        phone = legacy_phone(stay.mobile, stay.country_code)
        if phone and not person.phones.exists() and channels_writable(person.legacy_id):
            reconcile_primary_phone(person, phone)
            report.updated["person_phone"] += 1
        PastStay.objects.create(
            legacy_id=stay.stay_legacy_id,
            person=person,
            booking_number=stay.booking_number,
            villa_name=stay.villa_name[:255],
            property=Property.objects.filter(legacy_id=stay.villa_legacy_id).first(),
            year=stay.year,
            date_from=stay.date_from,
            date_to=stay.date_to,
            amount=stay.amount,
            currency=_currency(stay),
            notes=stay.notes,
        )
        report.created["past_stay"] += 1

    def _find_or_create_person(self, stay: ArchiveStay, report: SheetReport) -> Person:
        country = resolve_country(stay.country)
        if stay.country and country is None:
            report.skipped["country_unresolved"] += 1
            report.add_id("country_unresolved", _ids(stay))
        match = find_or_create_person(
            email=stay.email or None,
            first_name=stay.first_name,
            last_name=stay.last_name,
            legacy_id=person_legacy_id(stay.email, stay.first_name, stay.last_name),
            defaults={
                "title": stay.title[:16],
                "address_line_1": stay.address_line_1[:255],
                "address_line_2": stay.address_line_2[:255],
                "town": stay.town[:128],
                "post_code": stay.post_code[:32],
                "country": country,
            },
        )
        if match.inactive:
            raise _PersonSkipped("person_inactive")
        if match.ambiguous:
            raise _PersonSkipped("person_ambiguous")
        if match.created:
            report.created["person"] += 1
        elif match.filled:
            report.updated["person"] += 1
        return match.person
