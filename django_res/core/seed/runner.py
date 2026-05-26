"""Topological sort + execution of seed stages.

`run_stages(ctx, stages)` returns a list of `StageReport` in execution
order. Errors in a stage are captured on the report, not re-raised, so the
seeder always prints a full summary. The original command behaviour
(continue past errors, print summary) is preserved.
"""

from __future__ import annotations

import time

from core.seed.context import SeedContext
from core.seed.registry import Stage, StageReport


def _topo_sort(stages: list[Stage]) -> list[Stage]:
    """Stable topological sort: respect `depends_on`, otherwise registration
    order. Raises on missing dependencies or cycles so misconfiguration fails
    loud at startup, not silently mid-run."""

    by_name = {s.name: s for s in stages}
    for s in stages:
        for dep in s.depends_on:
            if dep not in by_name:
                raise ValueError(f"Stage {s.name!r} depends on unknown stage {dep!r}")

    resolved: list[Stage] = []
    resolved_names: set[str] = set()
    remaining = list(stages)
    while remaining:
        # Pick the first stage whose deps are all resolved — preserves the
        # registration order across the topo constraint.
        for s in remaining:
            if all(dep in resolved_names for dep in s.depends_on):
                resolved.append(s)
                resolved_names.add(s.name)
                remaining.remove(s)
                break
        else:
            unresolved = ", ".join(s.name for s in remaining)
            raise ValueError(f"Dependency cycle (or missing) among: {unresolved}")
    return resolved


def run_stages(ctx: SeedContext, stages: list[Stage]) -> list[StageReport]:
    reports: list[StageReport] = []
    for stage in _topo_sort(stages):
        report = StageReport(stage=stage.name)
        started = time.monotonic()
        try:
            report.created = stage.run(ctx)
        except Exception as exc:  # pragma: no cover — surfaced via report
            report.errors.append(repr(exc))
        report.duration_s = time.monotonic() - started
        reports.append(report)
    return reports
