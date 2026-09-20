"""GAP-112: relink customer-less legacy enquiries to the people the sheet
imports mint later in the cutover.

`EnquiryLoader` matches an enquiry's customer strictly, but the people it would
match only exist once `import_enquiry_sheet` has run. This module re-asks the
loader's own question afterwards. It is shared by the
`relink_enquiry_customers` command and its `reconcile_legacy` invariant.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from django.db.models import QuerySet

from accounts.enums import PersonStatus
from accounts.models import Person
from data_migration.loaders.sentinels import (
    ENQUIRY_PERSON_LEGACY_PREFIX,
    SHEET_LEGACY_PREFIX,
)
from data_migration.sheets.matching import match_person_by_email
from reservations.models import Enquiry

Category = Literal[
    "relinked", "no_email", "unmatched", "shared_email", "names_disagree", "inactive"
]

# `EnquiryLoader` stores this for a nameless row, after it has matched.
ANON_FIRST_NAME = "(anon)"


def enquiry_person_legacy_id(email: str) -> str:
    """`enquiry-person-<sha1>` over the normalised address (GAP-118 §3).

    Keyed on the address alone, unlike `sheets.matching.person_legacy_id`,
    which folds the names in so spouses sharing an inbox get distinct rows.
    Here the address IS the grouping: every unmatched enquiry carrying it
    becomes one customer, and a re-run derives the same key, which is what
    makes `--mint-unmatched` idempotent.
    """
    digest = hashlib.sha1((email or "").strip().lower().encode()).hexdigest()
    return f"{ENQUIRY_PERSON_LEGACY_PREFIX}{digest[:16]}"


def unlinked_legacy_enquiries() -> QuerySet[Enquiry]:
    """Customer-less enquiries `EnquiryLoader` wrote — never a sheet enquiry
    (always linked) nor one taken after go-live (legitimately anonymous)."""
    return (
        Enquiry.objects.filter(person__isnull=True, legacy_id__isnull=False)
        .exclude(legacy_id__startswith=SHEET_LEGACY_PREFIX)
        .order_by("pk")
    )


def classify_enquiry(enquiry: Enquiry) -> tuple[Category, Person | None]:
    """The strict `EnquiryLoader` match, vetoed when the address is shared.

    Returns the Person only for `relinked`. A shared address (any second
    holder, whatever their status or kind) is left for a human rather than
    letting the matcher's CUSTOMER-first tie-break guess.
    """
    addr = (enquiry.email or "").strip().lower()
    if "@" not in addr:
        return "no_email", None
    holders = list(Person.objects.filter(emails__email=addr))
    if not holders:
        return "unmatched", None
    if len(holders) > 1:
        return "shared_email", None
    first = enquiry.first_name
    if first == ANON_FIRST_NAME and not enquiry.last_name:
        first = ""
    person = match_person_by_email(
        addr, first_name=first, last_name=enquiry.last_name, active_only=True
    )
    if person is not None:
        return "relinked", person
    if holders[0].status != PersonStatus.ACTIVE:
        return "inactive", None
    return "names_disagree", None
