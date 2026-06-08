"""Advisory duplicate-Guest reporting for the legacy cutover.

No auto-merge — families and agency catch-alls legitimately share an address
(the in-repo demo dump's 135 enquiries collapse to 27 distinct emails). This
surfaces ACTIVE guests that share a normalized email or phone so an operator can
confirm and collapse via `Guest.merge()`. See people-model-cleanup.md.
"""

from __future__ import annotations

from collections import defaultdict

from reservations.enums import GuestStatus
from reservations.models.guest import Guest


def find_duplicate_candidates() -> list[list[Guest]]:
    """Return clusters (size > 1) of ACTIVE guests sharing an email or phone.

    Email and phone are independent grouping axes — a cluster is reported per
    shared channel value, never merged automatically.
    """
    by_key: dict[tuple[str, str], list[Guest]] = defaultdict(list)
    for guest in Guest.objects.filter(status=GuestStatus.ACTIVE.value):
        if guest.email:
            by_key[("email", guest.email)].append(guest)
        if guest.phone:
            by_key[("phone", guest.phone)].append(guest)
    return [members for members in by_key.values() if len(members) > 1]
