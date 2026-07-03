"""Unit tests for `accounts.enums` invariants."""

from __future__ import annotations

from accounts.enums import ContactRole, ContactType


def test_contact_type_mirrors_contact_role() -> None:
    # `contact_types` (ContactSerializer.get_contact_types) returns the union of
    # every property role with two synthetic capacities. ContactType is that
    # taxonomy: every ContactRole value must be expressible, and the only extra
    # is the synthetic "customer". This pins the AGENT collision (agent is in
    # both sets) and catches a new ContactRole added without a matching
    # ContactType member.
    assert set(ContactType.values) == set(ContactRole.values) | {"customer"}
