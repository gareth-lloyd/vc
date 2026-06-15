"""Seed-stage registry: importing this package wires every stage in.

Stage modules call `seeding.registry.register(...)` at import time. The
order of imports below also defines the default in-list ordering, which the
runner's stable topo-sort then respects when no `depends_on` constraint
forces a swap.
"""

from __future__ import annotations

# One-shot / canonical-row stages first.
# Core transactional graph.
from seeding.stages import (
    availability_blocks,  # noqa: F401
    bookings,  # noqa: F401
    collections,  # noqa: F401
    concierge_items,  # noqa: F401
    contacts,  # noqa: F401
    dashboard_activity,  # noqa: F401
    extra_quotations,  # noqa: F401
    features,  # noqa: F401
    gallery,  # noqa: F401
    groups,  # noqa: F401
    guest_preferences,  # noqa: F401
    ical_demo,  # noqa: F401
    integrations,  # noqa: F401
    nearby_places,  # noqa: F401
    notes,  # noqa: F401
    orphan_enquiries,  # noqa: F401
    owner_orgs,  # noqa: F401
    properties,  # noqa: F401
    property_lifecycle,  # noqa: F401
    refunds,  # noqa: F401
    rooms,  # noqa: F401
    system_setup,  # noqa: F401
    users,  # noqa: F401
    webhooks,  # noqa: F401
)
