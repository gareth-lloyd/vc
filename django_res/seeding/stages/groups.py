"""Pre-create a handful of PropertyGroups so multiple villas can share a
portfolio (instead of the legacy 1-to-1 SubFactory shape).

Each group keeps its all-null GroupSettings/GroupFinance (auto-created by
`properties.signals` on insert) — the `PropertySettings.effective()` chain
still resolves to None unless a later stage overrides it. That matches
production: most owners inherit the group default.

Skipped when `knobs.n_property_groups == 0` (e.g. the happy profile keeps
the legacy per-property group shape).
"""

from __future__ import annotations

from properties.factories import PropertyGroupFactory
from seeding.context import SeedContext
from seeding.registry import Stage, register


def _run(ctx: SeedContext) -> int:
    if ctx.knobs.n_property_groups <= 0:
        return 0
    for _ in range(ctx.knobs.n_property_groups):
        ctx.groups.append(PropertyGroupFactory())
    return ctx.knobs.n_property_groups


register(Stage(name="groups", run=_run))
