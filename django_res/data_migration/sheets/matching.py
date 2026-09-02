"""GAP-089: matching + normalisation helpers shared by the two spreadsheet
importers (`import_past_bookers`, `import_enquiry_sheet`).

Rules (design plan decisions 3-6, 8):

- **Person** (`find_or_create_person`): the importer's own ``legacy_id`` wins
  (re-run); else an ACTIVE Person sharing the e-mail *and* the normalised last
  name (first name must agree unless either side is blank) — same e-mail with a
  different name is a spouse and gets their own row; else, with no e-mail, the
  single ACTIVE Person with that exact name (customers preferred). Anything
  ambiguous creates a new row and says so. Matched rows are only ever
  *filled in* (blank fields set, never overwritten) so operator edits survive.
- **Villa** (`PropertyMatcher`): normalised name / display name, with a leading
  "villa" stripped on both sides; exactly one hit or nothing. No fuzzy match.
- **Geo**: ``Country`` via a small alias map then the ISO name list;
  ``Region`` by exact (country, name) with exactly one hit. Multi-valued cells
  ("Corfu / Paxos") resolve to nothing.
- **Tags**: the sheet vocabulary → `PersonTag`; unknown values are handed back
  for a notes line rather than dropped.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from django_countries import countries

from accounts.enums import PersonKind, PersonStatus, PersonTag
from accounts.models import Person
from accounts.services.person_channels import reconcile_primary_email
from properties.models import Country, Property, Region

_APOSTROPHES = re.compile(r"['\u2019`]")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")
_TAG_SPLIT = re.compile(r"[;,]")
_HTML_BREAK = re.compile(r"<\s*(?:br|/p|/div|/li)\s*/?\s*>", re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>]+>")
_MANY_NEWLINES = re.compile(r"\n{3,}")

#: Sheet tag token (casefolded) → PersonTag.
TAG_MAP: dict[str, PersonTag] = {
    "vip": PersonTag.VIP,
    "vip?": PersonTag.VIP,
    "pa": PersonTag.PA,
    "trade": PersonTag.TRADE,
    "nc": PersonTag.NICKS_FRIEND,
    "nwc": PersonTag.NICKS_NETWORK,
    "hnw": PersonTag.HNW,
    "owner": PersonTag.OWNER,
}

#: Free-text country spellings seen in the exports → ISO-3166 alpha-2. ``None``
#: means "known, but not a country we can store" (left null, reported).
COUNTRY_ALIASES: dict[str, str | None] = {
    "uk": "GB",
    "u.k.": "GB",
    "great britain": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "northern ireland": "GB",
    "usa": "US",
    "u.s.a.": "US",
    "us": "US",
    "united states": "US",
    "uae": "AE",
    "the netherlands": "NL",
    "holland": "NL",
    "channel islands": None,
    "jersey": "JE",
    "guernsey": "GG",
}


# --- pure helpers -----------------------------------------------------------


def normalise_name(value: Any) -> str:
    """Casefold, drop punctuation, collapse whitespace. ``None`` → ``""``."""
    if value is None:
        return ""
    text = _APOSTROPHES.sub("", str(value).casefold())
    text = _PUNCT.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def split_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    return [part.strip() for part in _TAG_SPLIT.split(str(raw)) if part.strip()]


def map_tags(raw: Any) -> tuple[list[PersonTag], list[str]]:
    """Return ``(known PersonTags in sheet order, unknown tokens verbatim)``."""
    known: list[PersonTag] = []
    unknown: list[str] = []
    for token in split_tags(raw):
        tag = TAG_MAP.get(token.casefold())
        if tag is None:
            unknown.append(token)
        elif tag not in known:
            known.append(tag)
    return known, unknown


def parse_sheet_date(value: Any) -> date | None:
    """A ``date`` from a date/datetime cell or an ISO / ``dd/mm/yyyy`` string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def html_to_text(value: Any) -> str:
    """Flatten the ``<br />``-laden Notes cells to plain text."""
    if value is None:
        return ""
    text = _HTML_BREAK.sub("\n", str(value))
    text = _HTML_TAG.sub("", text)
    text = html.unescape(text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _MANY_NEWLINES.sub("\n\n", text).strip()


def strip_villa_prefix(normalised: str) -> str:
    return (
        normalised.removeprefix("villa ").strip() if normalised.startswith("villa ") else normalised
    )


# --- villas ---------------------------------------------------------------


class PropertyMatcher:
    """Exact-after-normalisation villa-name lookup over every Property.

    The index is built once per run: each Property contributes its ``name`` and
    ``display_name`` both verbatim-normalised and with a leading "villa"
    stripped. A key that maps to more than one Property is ambiguous and never
    matches.
    """

    def __init__(self) -> None:
        index: dict[str, set[int]] = {}
        self._by_pk: dict[int, Property] = {}
        for prop in Property.objects.all():
            self._by_pk[prop.pk] = prop
            for raw in (prop.name, prop.display_name):
                norm = normalise_name(raw)
                if not norm:
                    continue
                for key in {norm, strip_villa_prefix(norm)}:
                    index.setdefault(key, set()).add(prop.pk)
        self._index = index

    def match(self, villa_name: Any) -> Property | None:
        norm = normalise_name(villa_name)
        if not norm or "/" in str(villa_name):
            return None
        for key in (norm, strip_villa_prefix(norm)):
            pks = self._index.get(key)
            if pks and len(pks) == 1:
                return self._by_pk[next(iter(pks))]
            if pks:
                return None  # ambiguous
        return None


# --- geo ------------------------------------------------------------------


def resolve_country(name: Any) -> Country | None:
    if name is None or not str(name).strip():
        return None
    key = str(name).strip().casefold()
    if key in COUNTRY_ALIASES:
        iso2 = COUNTRY_ALIASES[key]
    else:
        iso2 = countries.by_name(str(name).strip()) or None
    if not iso2:
        return None
    return Country.objects.filter(iso2=iso2).first()


def resolve_region(country_name: Any, region_name: Any) -> Region | None:
    if region_name is None or not str(region_name).strip() or "/" in str(region_name):
        return None
    if country_name is not None and "/" in str(country_name):
        return None
    qs = Region.objects.filter(name__iexact=str(region_name).strip())
    if country_name is not None and str(country_name).strip():
        qs = qs.filter(country__name__iexact=str(country_name).strip())
    hits = list(qs[:2])
    return hits[0] if len(hits) == 1 else None


# --- persons ---------------------------------------------------------------


def person_legacy_id(email: str | None, first: str | None, last: str | None) -> str:
    """`sheet-person-<sha1>` over (e-mail, normalised names) — shared by both
    importers so the same person in both workbooks converges on one key. The
    names are part of the key so spouses sharing an e-mail get distinct rows."""
    addr = (email or "").strip().lower()
    digest = hashlib.sha1(
        f"{addr}|{normalise_name(first)}|{normalise_name(last)}".encode()
    ).hexdigest()
    return f"sheet-person-{digest[:16]}"


@dataclass
class PersonMatch:
    person: Person
    created: bool
    ambiguous: bool = False
    filled: list[str] = field(default_factory=list)


def _names_agree(first_a: str, last_a: str, first_b: str, last_b: str) -> bool:
    if normalise_name(last_a) != normalise_name(last_b):
        return False
    fa, fb = normalise_name(first_a), normalise_name(first_b)
    return not fa or not fb or fa == fb


def fill_blanks(person: Person, defaults: dict[str, Any]) -> list[str]:
    """Set each field in ``defaults`` only where the Person's value is blank.

    Returns the field names that changed (unsaved — the caller saves).
    """
    changed: list[str] = []
    for name, value in defaults.items():
        if value in (None, ""):
            continue
        current = getattr(person, name)
        if current in (None, ""):
            setattr(person, name, value)
            changed.append(name)
    return changed


def find_or_create_person(
    *,
    email: str | None,
    first_name: str | None,
    last_name: str | None,
    legacy_id: str,
    defaults: dict[str, Any] | None = None,
) -> PersonMatch:
    """Resolve (or mint) the Person for a sheet row — see the module doc.

    ``defaults`` are model fields applied in full on create and blank-fill on
    match. The PRIMARY e-mail is reconciled on create only; a matched Person
    already carries this address (that is how it matched) or has none.
    """
    first = (first_name or "").strip()[:128]
    last = (last_name or "").strip()[:128]
    addr = (email or "").strip().lower()
    if "@" not in addr:
        addr = ""
    if not first and not last and not addr:
        raise ValueError("a sheet person needs a name or email")
    defaults = dict(defaults or {})

    existing = Person.objects.filter(legacy_id=legacy_id).first()
    ambiguous = False
    if existing is None and addr:
        for candidate in Person.objects.filter(
            emails__email=addr, status=PersonStatus.ACTIVE
        ).distinct():
            if _names_agree(first, last, candidate.first_name, candidate.last_name):
                existing = candidate
                break
    if existing is None and not addr:
        by_name = list(
            Person.objects.filter(
                status=PersonStatus.ACTIVE,
                first_name__iexact=first,
                last_name__iexact=last,
            )
        )
        if len(by_name) > 1:
            by_name = [p for p in by_name if p.kind == PersonKind.CUSTOMER]
        if len(by_name) == 1:
            existing = by_name[0]
        elif len(by_name) > 1:
            ambiguous = True

    if existing is not None:
        filled = fill_blanks(existing, defaults)
        if filled:
            existing.save(update_fields=[*filled, "updated_at"])
        return PersonMatch(existing, created=False, filled=filled)

    person = Person(
        first_name=first,
        last_name=last,
        legacy_id=legacy_id,
        kind=PersonKind.CUSTOMER,
    )
    for name, value in defaults.items():
        if value not in (None, ""):
            setattr(person, name, value)
    person.save()
    if addr:
        reconcile_primary_email(person, addr)
    return PersonMatch(person, created=True, ambiguous=ambiguous)


def append_note_line(person: Person, line: str) -> bool:
    """Append ``line`` to ``Person.notes`` unless already present verbatim.

    Saves and returns ``True`` when the notes changed.
    """
    text = (line or "").strip()
    if not text:
        return False
    current = person.notes or ""
    if text in current.splitlines() or (len(text.splitlines()) > 1 and text in current):
        return False
    person.notes = f"{current}\n{text}" if current else text
    person.save(update_fields=["notes", "updated_at"])
    return True
