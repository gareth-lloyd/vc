"""Stage registry + report types.

A `Stage` is a name, a list of prerequisite stage names, and a callable
that takes a `SeedContext` and returns an int row count. `register()` adds
one to the module-level `STAGES` list; the runner topo-sorts that list and
executes the stages in order.

The registry is import-driven: `core/seed/stages/__init__.py` re-exports
every stage module so importing the seed package wires them up. Stage
modules must avoid import-time side effects beyond calling `register()`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from core.seed.context import SeedContext

StageRunner = Callable[[SeedContext], int]


@dataclass(frozen=True)
class Stage:
    name: str
    run: StageRunner
    depends_on: tuple[str, ...] = ()


@dataclass
class StageReport:
    stage: str
    created: int = 0
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0


STAGES: list[Stage] = []


def register(stage: Stage) -> Stage:
    """Append `stage` to the registry. Duplicate names raise immediately."""

    if any(s.name == stage.name for s in STAGES):
        raise ValueError(f"Stage already registered: {stage.name}")
    STAGES.append(stage)
    return stage
