"""Server-side property scoping + visibility resolution for owner endpoints.

Every owner viewset filters its queryset on `owner_property_ids(user)` — the
client is never trusted to scope itself. Visibility flags resolve through
`owner_visibility_map`, which OR-merges across co-owning orgs (most-permissive
grant wins) so a user who reaches a villa through two orgs sees the union of
what either grant allows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from owners.enums import OwnerMembershipStatus, OwnerOrgStatus

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from accounts.models import User


class Visibility(TypedDict):
    view_full_money: bool
    view_guest_details: bool


def _active_grants(user: User) -> QuerySet:
    """Active `OwnerOrgProperty` rows reachable by `user`.

    A grant counts when: the user has an ACTIVE membership of the org, the
    org itself is ACTIVE, and the grant is open (`end_date IS NULL`).

    Do **not** add `.distinct()` here. `owner_visibility_map` relies on one
    row *per co-owning org* to drive its most-permissive-wins OR-merge;
    collapsing duplicates would silently pick a single org's flags.
    `owner_property_ids` dedups itself via `set()`.
    """
    from owners.models import OwnerOrgProperty

    return OwnerOrgProperty.objects.filter(
        end_date__isnull=True,
        organisation__status=OwnerOrgStatus.ACTIVE,
        organisation__memberships__user=user,
        organisation__memberships__status=OwnerMembershipStatus.ACTIVE,
    )


def owner_property_ids(user: User) -> set[int]:
    """The set of property ids `user` may view across all their active orgs."""
    return set(_active_grants(user).values_list("property_id", flat=True))


def owner_visibility_map(user: User) -> dict[int, Visibility]:
    """Per-property visibility flags, OR-merged across co-owning orgs.

    A property reached through two orgs gets the most-permissive flags of the
    two — visibility is a union, never an intersection.
    """
    merged: dict[int, Visibility] = {}
    for pid, full_money, guest_details in _active_grants(user).values_list(
        "property_id", "view_full_money", "view_guest_details"
    ):
        current = merged.get(pid)
        if current is None:
            merged[pid] = {
                "view_full_money": bool(full_money),
                "view_guest_details": bool(guest_details),
            }
        else:
            current["view_full_money"] = current["view_full_money"] or bool(full_money)
            current["view_guest_details"] = current["view_guest_details"] or bool(guest_details)
    return merged
