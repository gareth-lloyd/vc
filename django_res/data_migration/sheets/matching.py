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
- **E-mail** (`normalise_sheet_email`): an apostrophe typed for ``@`` (the
  same key on a UK layout) is repaired; every other cell is left to the
  importer's own ``"@" not in email`` check.
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

from django.db.models import Case, Value, When
from django_countries import countries

from accounts.enums import PersonKind, PersonStatus, PersonTag
from accounts.models import Person
from accounts.services.person_channels import reconcile_primary_email
from data_migration.loaders.sentinels import CLIENT_LEGACY_PREFIX, SHEET_LEGACY_PREFIX
from properties.enums import PropertyStatus
from properties.models import Country, Property, Region

_APOSTROPHES = re.compile(r"['\u2019`]")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")
_TAG_SPLIT = re.compile(r"[;,]")
_HTML_BREAK = re.compile(r"<\s*(?:br|/p|/div|/li)\s*/?\s*>", re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>]+>")
_MANY_NEWLINES = re.compile(r"\n{3,}")
#: `local@domain.tld` with no whitespace — the shape a repaired cell must
#: have before `normalise_sheet_email` accepts it.
_EMAIL_SHAPE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")

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


def normalise_sheet_email(value: Any) -> str:
    """An e-mail cell, with the one keying slip the exports carry repaired.

    On a UK layout ``@`` is Shift + the apostrophe key, so an unshifted press
    writes ``chloe'k2pdg.com.au`` where ``chloe@k2pdg.com.au`` was meant. A
    cell with no ``@`` and exactly one apostrophe is that slip and nothing
    else; anything other than that shape (a real address, ``Rose Mann``,
    ``No email``) is handed back unchanged for the caller's own validation.
    """
    text = "" if value is None else str(value).strip()
    if "@" in text or text.count("'") != 1:
        return text
    repaired = text.replace("'", "@")
    # Only when the result is address-shaped: the column also holds prose
    # ("don't have one") and apostrophe surnames, and a repair that passed the
    # importer's `"@" not in email` guard would become a real PersonEmail and
    # a person-matching key.
    return repaired if _EMAIL_SHAPE.fullmatch(repaired) else text


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
    # Drop a time suffix ("1/6/2019 00:00", "2019-06-01T09:15") before parsing
    # so single-digit day/month strings are not clipped mid-token.
    head = text.split()[0].split("T")[0]
    try:
        return date.fromisoformat(head)
    except ValueError:
        pass
    try:
        return datetime.strptime(head, "%d/%m/%Y").date()
    except ValueError:
        return None


def html_to_text(value: Any) -> str:
    """Flatten the ``<br />``-laden Notes cells to plain text.

    Deliberately not `comms.compilers.html_to_plaintext`: that one is
    html2text (Markdown-flavoured — it escapes ``- `` / ``1. `` list markers),
    which is right for e-mail bodies and wrong for notes cells that should read
    exactly as Nick typed them.
    """
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
    """Exact-after-normalisation villa-name lookup, live villas first.

    The indexes are built once per run: each Property contributes its ``name``
    and ``display_name`` both verbatim-normalised and with a leading "villa"
    stripped. A key that maps to more than one Property is ambiguous and never
    matches.

    BUG-030 §33: legacy holds archived duplicates of one villa ("villa yeraki"
    x34), which made most sheet names ambiguous. So a name is looked up among
    non-ARCHIVED properties first; only a name with no hit there falls back to
    every property (a villa that exists only archived still links). The exact
    name is tried before the "villa"-stripped one. Two live namesakes stay
    ambiguous.
    """

    def __init__(self) -> None:
        self._by_pk: dict[int, Property] = {}
        self._live_index: dict[str, set[int]] = {}
        self._index: dict[str, set[int]] = {}
        for prop in Property.objects.all():
            self._by_pk[prop.pk] = prop
            indexes = [self._index]
            if prop.status != PropertyStatus.ARCHIVED:
                indexes.append(self._live_index)
            for raw in (prop.name, prop.display_name):
                norm = normalise_name(raw)
                if not norm:
                    continue
                for key in {norm, strip_villa_prefix(norm)}:
                    for index in indexes:
                        index.setdefault(key, set()).add(prop.pk)

    def match(self, villa_name: Any) -> Property | None:
        norm = normalise_name(villa_name)
        if not norm or "/" in str(villa_name):
            return None
        # Per key: the exact name before the "villa"-stripped one, and for
        # each, live villas before all villas.
        for key in (norm, strip_villa_prefix(norm)):
            for index in (self._live_index, self._index):
                pks = index.get(key)
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
        # Through `resolve_country` so the sheet's aliases ("UK", "Holland",
        # "USA") scope the lookup the same way they resolve `Person.country`;
        # a country we cannot place means a region we cannot trust.
        country = resolve_country(country_name)
        if country is None:
            return None
        qs = qs.filter(country=country)
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
    #: The row's own `legacy_id` resolved to a Person that is no longer ACTIVE
    #: (anonymised / deactivated after an earlier run). Nothing was written;
    #: the caller must not append notes or channels either.
    inactive: bool = False


def _names_agree(first_a: str, last_a: str, first_b: str, last_b: str) -> bool:
    """Same e-mail, same person? Last names must agree unless one side has
    none (an e-mail-only row), and likewise for first names. Two different
    last names on one address is the spouse case → a new Person."""
    la, lb = normalise_name(last_a), normalise_name(last_b)
    if la and lb and la != lb:
        return False
    fa, fb = normalise_name(first_a), normalise_name(first_b)
    return not fa or not fb or fa == fb


def fill_blanks(person: Person, defaults: dict[str, Any]) -> list[str]:
    """Set each field in ``defaults`` only where the Person's value is blank.

    Returns the field names that changed (unsaved — the caller saves).
    """
    changed: list[str] = []
    for name, value in defaults.items():
        if _is_blank(value):
            continue
        if _is_blank(getattr(person, name)):
            setattr(person, name, value)
            changed.append(name)
    return changed


def _is_blank(value: Any) -> bool:
    # `[]` covers ArrayField defaults (tags) so list-valued defaults blank-fill
    # a matched Person exactly as they apply on create.
    return value is None or value == "" or value == []


def match_person_by_name(first: str, last: str) -> tuple[Person | None, bool]:
    """The no-e-mail rule, shared by both importers: exactly one ACTIVE
    CUSTOMER with this (first, last), else ``(None, ambiguous)``.

    BUG-030 §35: a sheet guest is a customer, so an owner/agent namesake is
    never linked — not even a single one. ``ambiguous`` is True whenever an
    ACTIVE namesake exists that did not resolve to one customer (several
    customers, or only non-customers), so the caller flags it rather than
    silently linking or duplicating."""
    by_name = list(
        Person.objects.filter(
            status=PersonStatus.ACTIVE, first_name__iexact=first, last_name__iexact=last
        )
    )
    customers = [p for p in by_name if p.kind == PersonKind.CUSTOMER]
    if len(customers) == 1:
        return customers[0], False
    return None, bool(by_name)


def match_person_by_email(
    addr: str | None,
    *,
    first_name: str = "",
    last_name: str = "",
    active_only: bool,
) -> Person | None:
    """The Person carrying ``addr`` on ANY of their e-mails (not only the
    primary: a secondary address is still theirs) whose names agree.

    BUG-030 §18: one human can be both a CUSTOMER (`client-`) and a CONTACT
    (owner/agent) on the same address, so the order is deterministic — ACTIVE
    first, then CUSTOMER before CONTACT, then oldest pk. ``active_only=False``
    keeps a deactivated person matchable (the sheet importers report them as
    `inactive` rather than re-minting them); the legacy EnquiryLoader links
    only ACTIVE people.
    """
    addr = (addr or "").strip().lower()
    if "@" not in addr:
        return None
    candidates = Person.objects.filter(emails__email=addr)
    if active_only:
        candidates = candidates.filter(status=PersonStatus.ACTIVE)
    customer_first = Case(When(kind=PersonKind.CUSTOMER, then=Value(0)), default=Value(1))
    for candidate in candidates.order_by("status", customer_first, "pk"):
        if _names_agree(first_name, last_name, candidate.first_name, candidate.last_name):
            return candidate
    return None


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
        # Any status: a deactivated person who still carries this address must
        # come back as `inactive`, not be re-minted from the sheet. (A fully
        # anonymised person has no e-mail or name left to match — see the
        # CUTOVER note on re-runs after an erasure.)
        existing = match_person_by_email(addr, first_name=first, last_name=last, active_only=False)
    if existing is None and not addr:
        existing, ambiguous = match_person_by_name(first, last)
        # A deactivated namesake comes back `inactive` unless the name is
        # genuinely ambiguous among ACTIVE customers; an active owner/agent
        # namesake alone (ambiguous for §35) must not hide it.
        several_active_customers = (
            ambiguous
            and Person.objects.filter(
                status=PersonStatus.ACTIVE,
                kind=PersonKind.CUSTOMER,
                first_name__iexact=first,
                last_name__iexact=last,
            ).exists()
        )
        if existing is None and not several_active_customers:
            existing = (
                Person.objects.filter(first_name__iexact=first, last_name__iexact=last)
                .exclude(status=PersonStatus.ACTIVE)
                .first()
            )
    if existing is not None and existing.status != PersonStatus.ACTIVE:
        # Minted or matched by an earlier run and since anonymised /
        # deactivated: a re-run must not write the sheet's PII back onto it.
        return PersonMatch(existing, created=False, inactive=True)

    if existing is not None:
        filled = fill_blanks(existing, defaults)
        if filled:
            existing.save(update_fields=[*filled, "updated_at"])
        return PersonMatch(existing, created=False, filled=filled)

    person = Person(
        # A nameless row (e-mail only) would render as "Client #id"; the
        # address stands in as the first name. Matching above used the raw
        # (blank) names, so re-runs still resolve via legacy_id / e-mail.
        first_name=first or ("" if last else addr[:128]),
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


def channels_writable(legacy_id: str | None) -> bool:
    """Sheet- and client-keyed people (and hand-made ones) may gain a channel;
    a legacy owner/agent Person (bare VillaContact id) may not, or the
    PersonPhone reconcile count would drift from VillaContactTele."""
    return legacy_id is None or legacy_id.startswith((SHEET_LEGACY_PREFIX, CLIENT_LEGACY_PREFIX))
