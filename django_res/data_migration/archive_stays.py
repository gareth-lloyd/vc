"""GAP-113: legacy `VillaArchiveBookings` → dated `PastStay` rows.

Staff re-keyed many Past Bookers sheet stays into this legacy table (Dec-2025 →
Mar-2026) with what the sheet lacks: exact dates, the amount as recorded, its
currency and the guest's contact details. This module is the pure reading of
those rows, shared by the `import_archive_stays` command and its
`reconcile_legacy` invariant — each fetches rows through its own cursor.

Parsing is deliberately literal: `CurrencyId 0` and `Amount 0` mean "not
recorded" (NULL, never a guessed villa currency), and implausible dates
(reversed, zero nights, > `MAX_NIGHTS`) are dropped rather than landed on a
stay the constraint would reject — the stay still lands with its year.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from accounts.enums import PersonKind, PersonStatus
from accounts.models import Person
from data_migration.loaders._util import legacy_deleted_sql
from data_migration.sheets.matching import normalise_name
from reservations.models import PastStay

ARCHIVE_STAY_PREFIX = "archive-stay-"

# Id 297 is a staff test entry (From = To, placeholder guest).
ARCHIVE_TEST_ROW_IDS = frozenset({297})

# Longer than any real villa stay; the three rows above it (149 to 255 nights)
# are keying slips.
MAX_NIGHTS = 45

ARCHIVE_ROWS_SQL = f"""
SELECT b.Id, b.FromDate, b.ToDate, b.Amount, b.CurrencyId, b.VillaId,
       v.Name AS VillaName, b.Notes, b.Title, b.FirstName, b.LastName, b.Email,
       b.CountryCode, b.MobileNo, b.Town, b.Country, b.Postcode,
       b.Addressline1, b.Addressline2
FROM VillaArchiveBookings b
LEFT JOIN VillaMaster v ON v.Id = b.VillaId
WHERE NOT {legacy_deleted_sql("b.")}
ORDER BY b.Id
"""

# `BN1063`, `bn 1004a`, `BN0659` → "1063", "1004a", "659". The letter suffix
# is a distinct re-issued booking, so it is kept.
_BN = re.compile(r"BN\s*0*(\d+[a-z]?)", re.IGNORECASE)


def bn_token(text: str | None) -> str:
    """The first booking number in free text (lower-cased), else ""."""
    match = _BN.search(text or "")
    return match.group(1).lower() if match else ""


def leading_bn_token(booking_number: str) -> str:
    """The sheet's booking number token — only a LEADING one, so the tails in
    `BN443 (422)` / `BN450 / 510` never match another stay."""
    match = _BN.match(booking_number.strip())
    return match.group(1).lower() if match else ""


@dataclass(frozen=True)
class ArchiveStay:
    """One stay: a group of re-saved rows, carrying its highest-Id row."""

    legacy_id: int
    member_ids: tuple[int, ...]
    villa_legacy_id: str
    villa_name: str
    year: int
    date_from: date | None
    date_to: date | None
    amount: Decimal | None
    currency_legacy_id: str | None
    bn: str
    notes: str
    title: str
    first_name: str
    last_name: str
    email: str
    country_code: str
    mobile: str
    town: str
    country: str
    post_code: str
    address_line_1: str
    address_line_2: str
    dates_dropped: bool
    # The dates exactly as keyed (before any drop) — what re-saves are
    # compared on.
    keyed_from: date
    keyed_to: date | None
    duplicate_conflict: bool = False

    @property
    def booking_number(self) -> str:
        return f"BN{self.bn}" if self.bn else ""

    @property
    def stay_legacy_id(self) -> str:
        return f"{ARCHIVE_STAY_PREFIX}{self.legacy_id}"


@dataclass
class GroupResult:
    stays: list[ArchiveStay] = field(default_factory=list)
    test_row_ids: list[int] = field(default_factory=list)
    errors: list[tuple[int, str]] = field(default_factory=list)


def _text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    return str(value).strip() if value is not None else ""


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def parse_row(row: dict[str, Any]) -> ArchiveStay:
    """One live legacy row → a single-member stay. Raises `ValueError`."""
    legacy_id = int(row["Id"])
    date_from = _as_date(row.get("FromDate"))
    if date_from is None:
        raise ValueError("missing FromDate")
    keyed_from, keyed_to = date_from, _as_date(row.get("ToDate"))
    date_to = keyed_to
    dates_dropped = date_to is None or not 0 < (date_to - date_from).days <= MAX_NIGHTS
    if dates_dropped:
        date_from = date_to = None

    raw_amount = row.get("Amount")
    amount = Decimal(str(raw_amount)).quantize(Decimal("0.01")) if raw_amount else None
    currency_id = row.get("CurrencyId")

    notes = _text(row, "Notes")
    match = _BN.search(notes)
    if match:
        notes = (notes[: match.start()] + notes[match.end() :]).strip()
    email = _text(row, "Email").lower()

    return ArchiveStay(
        legacy_id=legacy_id,
        member_ids=(legacy_id,),
        villa_legacy_id=_text(row, "VillaId"),
        villa_name=_text(row, "VillaName"),
        year=keyed_from.year,
        date_from=date_from,
        date_to=date_to,
        amount=amount or None,
        currency_legacy_id=str(currency_id) if currency_id else None,
        bn=match.group(1).lower() if match else "",
        notes=notes,
        title=_text(row, "Title"),
        first_name=_text(row, "FirstName"),
        last_name=_text(row, "LastName"),
        email=email if "@" in email else "",
        country_code=_text(row, "CountryCode"),
        mobile=_text(row, "MobileNo"),
        town=_text(row, "Town"),
        country=_text(row, "Country"),
        post_code=_text(row, "Postcode"),
        address_line_1=_text(row, "Addressline1"),
        address_line_2=_text(row, "Addressline2"),
        dates_dropped=dates_dropped,
        keyed_from=keyed_from,
        keyed_to=keyed_to,
    )


def _span(stay: ArchiveStay) -> tuple[date, date]:
    end = stay.keyed_to if stay.keyed_to and stay.keyed_to > stay.keyed_from else None
    return stay.keyed_from, end or stay.keyed_from + timedelta(days=1)


def same_stay(a: ArchiveStay, b: ArchiveStay) -> bool:
    """Are two legacy rows re-saves of one stay?

    Same villa and overlapping keyed dates (a re-save may correct a date), and
    then: the same booking number when both carry one (two different numbers
    are two bookings — `BN1005` / `BN1005a`); otherwise the same guest by
    e-mail or surname (a re-save may add the number or change the address).
    """
    if a.villa_legacy_id != b.villa_legacy_id:
        return False
    (a_from, a_to), (b_from, b_to) = _span(a), _span(b)
    if not (a_from < b_to and b_from < a_to):
        return False
    if a.bn and b.bn:
        return a.bn == b.bn
    if a.email and a.email == b.email:
        return True
    last = normalise_name(a.last_name)
    return bool(last) and last == normalise_name(b.last_name)


def _merge(members: list[ArchiveStay]) -> ArchiveStay:
    """The highest `Id` (the latest re-key) represents the stay; the booking
    number and e-mail are the latest non-empty ones (a later re-save may have
    dropped them). Members disagreeing on the money, the dates or the number
    are flagged for the report."""
    members = sorted(members, key=lambda s: s.legacy_id)
    representative = members[-1]
    facts = {(s.amount, s.currency_legacy_id, s.keyed_from, s.keyed_to) for s in members}
    numbers = {s.bn for s in members if s.bn}
    return replace(
        representative,
        member_ids=tuple(s.legacy_id for s in members),
        bn=next((s.bn for s in reversed(members) if s.bn), ""),
        email=next((s.email for s in reversed(members) if s.email), ""),
        duplicate_conflict=len(facts) > 1 or len(numbers) > 1,
    )


def group_rows(rows: list[dict[str, Any]]) -> GroupResult:
    """Parse live rows and collapse re-saves of one stay (`same_stay`,
    transitively). Two guests on the same villa + dates stay apart."""
    result = GroupResult()
    parsed: list[ArchiveStay] = []
    for row in sorted(rows, key=lambda r: int(r["Id"])):
        legacy_id = int(row["Id"])
        if legacy_id in ARCHIVE_TEST_ROW_IDS:
            result.test_row_ids.append(legacy_id)
            continue
        try:
            parsed.append(parse_row(row))
        except ValueError as exc:
            result.errors.append((legacy_id, str(exc)))

    groups: list[list[ArchiveStay]] = []
    for stay in parsed:
        joined = [g for g in groups if any(same_stay(stay, member) for member in g)]
        merged = [stay]
        for group in joined:
            merged.extend(group)
            groups.remove(group)
        groups.append(merged)

    result.stays = sorted((_merge(g) for g in groups), key=lambda s: s.legacy_id)
    return result


# --- classification against the sheet-imported stays ----------------------

SHEET_STAY_PREFIX = "sheet-stay-"

Category = Literal[
    "exists",
    "enrich",
    "create",
    "ambiguous",
    "bn_year_conflict",
    "weak_conflict",
    "target_taken",
    "target_contested",
]


@dataclass(frozen=True)
class Classification:
    stay: ArchiveStay
    category: Category
    #: `enrich`: the sheet stay to blank-fill; `exists`: the row carrying it.
    target: PastStay | None = None
    #: The single ACTIVE CUSTOMER holding the stay's e-mail, if any — the
    #: person a `create` attaches to.
    email_person: Person | None = None
    #: A booking-number match whose sheet stay is linked to another villa
    #: (staff mis-keyed villas); enriched anyway, reported.
    property_differs: bool = False


@dataclass
class _SheetStays:
    by_bn: dict[str, list[PastStay]] = field(default_factory=dict)
    by_person_year: dict[tuple[int, int | None], list[PastStay]] = field(default_factory=dict)
    by_year: dict[int | None, list[PastStay]] = field(default_factory=dict)

    @classmethod
    def load(cls) -> _SheetStays:
        index = cls()
        rows = (
            PastStay.objects.filter(legacy_id__startswith=SHEET_STAY_PREFIX)
            .select_related("person", "property", "currency")
            .order_by("pk")
        )
        for row in rows:
            token = leading_bn_token(row.booking_number)
            if token:
                index.by_bn.setdefault(token, []).append(row)
            index.by_person_year.setdefault((row.person_id, row.year), []).append(row)
            index.by_year.setdefault(row.year, []).append(row)
        return index


def _email_person(addr: str) -> Person | None:
    """The address's only holder, when that holder is an ACTIVE CUSTOMER.
    Names are not compared: re-keys carry surname typos (Coppersmith), and a
    shared address (any second holder) is left to the name tier instead."""
    if not addr:
        return None
    holders = list(Person.objects.filter(emails__email=addr).distinct()[:2])
    if len(holders) != 1:
        return None
    holder = holders[0]
    if holder.status != PersonStatus.ACTIVE or holder.kind != PersonKind.CUSTOMER:
        return None
    return holder


def _at_villa(stay: ArchiveStay, sheet_stay: PastStay) -> bool:
    prop = sheet_stay.property
    return prop is None or prop.legacy_id == stay.villa_legacy_id


def _pick(stay: ArchiveStay, candidates: list[PastStay]) -> tuple[Category | None, PastStay | None]:
    """A weak (no booking number) tier. A sheet stay under another booking
    number is another booking (Gibbens `BN1005` / `BN1005a`), not a candidate;
    of the rest only a stay at this villa, or one the sheet left unlinked (its
    villa names rarely match `VillaMaster` — "Koufalos" / "Koufalos House"),
    can be the same stay."""
    if stay.bn:
        candidates = [c for c in candidates if leading_bn_token(c.booking_number) in ("", stay.bn)]
    if not candidates:
        return None, None
    fitting = [c for c in candidates if _at_villa(stay, c)]
    if not fitting:
        return "weak_conflict", None
    if len(fitting) > 1:
        return "ambiguous", None
    return "enrich", fitting[0]


def _match(
    stay: ArchiveStay, sheet: _SheetStays, holder: Person | None
) -> tuple[Category, PastStay | None]:
    if stay.bn and (hits := sheet.by_bn.get(stay.bn)):
        same_year = [h for h in hits if h.year == stay.year]
        if not same_year:
            return "bn_year_conflict", None
        if len(same_year) > 1:
            return "ambiguous", None
        return "enrich", same_year[0]
    if holder is not None:
        category, target = _pick(stay, sheet.by_person_year.get((holder.pk, stay.year), []))
        if category:
            return category, target
    first, last = normalise_name(stay.first_name), normalise_name(stay.last_name)
    if first and last:
        namesakes = [
            s
            for s in sheet.by_year.get(stay.year, [])
            if normalise_name(s.person.first_name) == first
            and normalise_name(s.person.last_name) == last
        ]
        category, target = _pick(stay, namesakes)
        if category:
            return category, target
    return "create", None


def notes_pending(stay: ArchiveStay, target: PastStay) -> bool:
    """The archive notes are appended once, as whole lines — a shorter note
    that merely occurs inside the sheet's ("Paid" in "Paid by card") is still
    pending."""
    return bool(stay.notes) and f"\n{stay.notes}\n" not in f"\n{target.notes}\n"


def _fill_state(stay: ArchiveStay, target: PastStay) -> Literal["pending", "done", "taken"]:
    """Blank-fill semantics: a fact already set to another value is someone
    else's (`taken`); nothing left to fill is `done`."""
    currency = target.currency.legacy_id if target.currency is not None else None
    pairs = [
        (target.date_from, stay.date_from),
        (target.date_to, stay.date_to),
        (target.amount, stay.amount),
        (currency, stay.currency_legacy_id),
    ]
    if any(have is not None and want is not None and have != want for have, want in pairs):
        return "taken"
    if any(have is None and want is not None for have, want in pairs):
        return "pending"
    return "pending" if notes_pending(stay, target) else "done"


def classify(stays: list[ArchiveStay]) -> list[Classification]:
    """What the importer should do with each stay (read-only, input order).

    Tiers, first hit wins: an `archive-stay-<Id>` row already created → exists;
    the stay's booking number against the sheet stays' leading numbers (same
    year, villa ignored — reported when it differs); the e-mail's single ACTIVE
    CUSTOMER's sheet stays that year; sheet stays that year whose person has
    the same first and last name. No hit → `create`. A sheet stay claimed by
    more than one archive stay is `target_contested` for all of them — never
    first-wins, so the outcome does not depend on order.
    """
    sheet = _SheetStays.load()
    created = {
        row.legacy_id: row
        for row in PastStay.objects.filter(legacy_id__startswith=ARCHIVE_STAY_PREFIX)
    }

    matched: list[tuple[ArchiveStay, Category, PastStay | None, Person | None]] = []
    for stay in stays:
        holder = _email_person(stay.email)
        if stay.stay_legacy_id in created:
            matched.append((stay, "exists", created[stay.stay_legacy_id], holder))
            continue
        category, target = _match(stay, sheet, holder)
        matched.append((stay, category, target, holder))

    claims = Counter(
        target.pk for _, category, target, _ in matched if category == "enrich" and target
    )
    results: list[Classification] = []
    for stay, category, target, holder in matched:
        if category != "enrich" or target is None:
            results.append(Classification(stay, category, target, holder))
            continue
        differs = not _at_villa(stay, target)
        if claims[target.pk] > 1:
            results.append(Classification(stay, "target_contested", None, holder))
            continue
        state = _fill_state(stay, target)
        if state == "taken":
            results.append(Classification(stay, "target_taken", None, holder))
        else:
            final: Category = "enrich" if state == "pending" else "exists"
            results.append(Classification(stay, final, target, holder, differs))
    return results
