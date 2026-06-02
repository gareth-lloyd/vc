"""Seed-dev package — split out of the `seed_dev` management command.

`seeding.context.SeedContext` carries per-run state (rng, profile knobs,
shared collections). `seeding.registry.Stage` + `register` give each stage
a name and a dependency list; `seeding.runner.run_stages` topo-sorts and
executes them.

The management command (`seeding/management/commands/seed_dev.py`) is the only
public surface — same CLI flags as before. Everything else here is internal
plumbing.
"""

from __future__ import annotations

from seeding.context import _PROFILES, _SCALES, Profile, ProfileKnobs, SeedContext
from seeding.registry import STAGES, Stage, StageReport, register
from seeding.runner import run_stages

__all__ = [
    "STAGES",
    "_PROFILES",
    "_SCALES",
    "Profile",
    "ProfileKnobs",
    "SeedContext",
    "Stage",
    "StageReport",
    "register",
    "run_stages",
]
