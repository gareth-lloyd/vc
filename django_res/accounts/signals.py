from __future__ import annotations

import django.dispatch

# GAP-081: fired at the end of `Person.merge` (still inside its transaction)
# with kwargs `survivor` (the surviving Person) and `absorbed_pk` (the merged
# row's now-dead pk). The merge rewrites FKs via `.update()` — which fires no
# post_save — so downstream apps (integrations, reservations) listen here to
# re-enqueue CRM pushes for the survivor and any repointed rows.
person_merged = django.dispatch.Signal()


def _register() -> None:
    """Register app signal handlers. Filled in per app."""
