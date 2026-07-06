"""Best-effort, positives-only enrichment of GAP-064 room attributes from prose.

A keyword pass over `Room.website_description` and the preserved legacy
placement string `Room.placement_note` (GAP-065 — the legacy field crammed
amenity facts like "First floor - King, hairdryer" into the location box)
creates `RoomAttributeAssignment` rows for confident matches and fills
`ensuite_type` from explicit "en-suite shower/bath" phrasing — only when the
facet is currently unknown (`""`). It never infers an absence, never removes
an assignment, and never overwrites curator data, so re-running (e.g. after
a cutover delta load) is always safe. Source prose is retained on the Room,
so a missed keyword loses nothing — this is convenience, not a correctness
dependency.

It also re-invokes `sync_room_attributes()` first, so the catalog's
`implies_property_feature` candidate links (a no-op at migrate time — Features
are not migration-seeded) attach once legacy/seeded Features exist.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from django.core.management.base import BaseCommand

from properties.enums import EnsuiteType
from properties.models import Room, RoomAttribute, RoomAttributeAssignment
from properties.room_attribute_catalog import sync_room_attributes

# slug -> alternation of confident phrasings (case-insensitive). Deliberately
# conservative: a generic word ("safe", "fan") only counts with a qualifier.
_KEYWORDS: dict[str, str] = {
    "aircon": r"\bair[- ]?con(?:dition\w*)?\b|\ba/c\b",
    "ceiling_fan": r"(?:ceiling|overhead) fan",
    "sea_view": r"sea[- ]?views?",
    "balcony": r"balcon(?:y|ies)",
    "terrace": r"terrace",
    "wheelchair": r"wheelchair",
    "in_room_safe": r"(?:in[- ]room|personal|electronic|laptop) safe|\bsafe box\b",
    "hairdryer": r"hair[- ]?dr[iy]er",
    "mini_fridge": r"mini[- ]?(?:fridge|bar)\b",
}

_ENSUITE = re.compile(r"en[- ]?suite", re.IGNORECASE)
_SHOWER = re.compile(r"\bshower", re.IGNORECASE)
# "bath"/"bathtub" as a fixture, not linen ("bath towels") or garments
# ("bathrobe" never matches — no boundary inside the word).
_BATH = re.compile(r"\bbath(?:tub|\s+tub)?\b(?!\s+(?:towels?|sheets?|mats?|robes?))", re.IGNORECASE)
_SENTENCES = re.compile(r"[.!?\n]+")


def _ensuite_type_from(text: str) -> str:
    """Confident facet from prose; "" when not stated. Reads shower/bath words
    only from the sentence(s) that mention "en-suite" (positives only —
    an unrelated "a bath is available down the hall" must not couple in)."""
    relevant = " ".join(s for s in _SENTENCES.split(text) if _ENSUITE.search(s))
    if not relevant:
        return ""
    has_shower = bool(_SHOWER.search(relevant))
    has_bath = bool(_BATH.search(relevant))
    if has_shower and has_bath:
        return EnsuiteType.BOTH
    if has_shower:
        return EnsuiteType.SHOWER
    if has_bath:
        return EnsuiteType.BATH
    return ""


class Command(BaseCommand):
    help = (
        "Positives-only keyword backfill of room amenity assignments and the "
        "ensuite_type facet from website_description and placement_note "
        "(GAP-064/GAP-065). Idempotent; never overwrites curator data."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be created/set without writing.",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        dry_run: bool = opts["dry_run"]

        # Ensure the starter catalog exists and attach implies-feature
        # candidate links now that Features may exist (set-if-NULL). Runs in
        # dry-run mode too — the preview must see the same catalog a real run
        # would, or it under-reports; the sync is idempotent and touches only
        # the canonical starter rows, never room data.
        sync_room_attributes()

        patterns = {slug: re.compile(regex, re.IGNORECASE) for slug, regex in _KEYWORDS.items()}
        attributes = {a.slug: a for a in RoomAttribute.objects.filter(slug__in=patterns)}

        assigned: Counter[str] = Counter()
        ensuite_set = 0
        rooms = Room.objects.exclude(website_description="", placement_note="")
        for room in rooms.iterator():
            # Newline join = a sentence boundary for `_ensuite_type_from`, so
            # note vocabulary never merges into a trailing description
            # sentence ("… en-suite" + "… Shower room nearby" must not couple).
            text = "\n".join(t for t in (room.website_description, room.placement_note) if t)
            for slug, pattern in patterns.items():
                if slug not in attributes or not pattern.search(text):
                    continue
                if dry_run:
                    exists = RoomAttributeAssignment.objects.filter(
                        room=room, attribute=attributes[slug]
                    ).exists()
                    created = not exists
                else:
                    _, created = RoomAttributeAssignment.objects.get_or_create(
                        room=room, attribute=attributes[slug]
                    )
                if created:
                    assigned[slug] += 1
            if room.ensuite_type == "":
                ensuite_type = _ensuite_type_from(text)
                if ensuite_type:
                    ensuite_set += 1
                    if not dry_run:
                        room.ensuite_type = ensuite_type
                        # The DB constraint (and the semantics): typed = ensuite.
                        room.is_ensuite = True
                        room.save(update_fields=["ensuite_type", "is_ensuite"])

        prefix = "[dry-run] would create" if dry_run else "created"
        for slug in _KEYWORDS:
            self.stdout.write(f"{prefix} {assigned[slug]:>5} x {slug}")
        self.stdout.write(
            f"{'[dry-run] would set' if dry_run else 'set'} ensuite_type on {ensuite_set} room(s)"
        )
