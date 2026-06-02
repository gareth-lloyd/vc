"""Shared factory-boy support primitives.

`core` is the foundation layer, so a seed/test primitive imported by *every*
app's factories belongs here rather than in any one domain app — keeping the
factory modules' cross-app imports pointing down into `core`.
"""

from __future__ import annotations

from uuid import uuid4

# `factory.Sequence` is an in-process counter — it restarts at 0 every command
# invocation, so a bare `f"villa-{n}"` collides with rows a previous run already
# wrote. This per-process token keeps additive `seed_dev` re-runs unique while
# in-process builds stay unique via `n`. Imported by every app's factories.
RUN_TOKEN = uuid4().hex[:8]
