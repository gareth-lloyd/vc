> **✅ RESOLVED (2026-06-15)** — Problem: The owners app sat outside the import-linter layers contract. Fix: Inserted owners into the spine between reservations and pricing. Commit: 8f1c474.
>
> _Original ticket preserved below for context._

# FG-013 — `owners` app sits outside the import-linter layers contract

- **Severity:** 🟠 Footgun
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `pyproject.toml:144–156` (root_packages), `pyproject.toml:188–196` (layers)

## Problem

`owners` is listed in import-linter `root_packages` (pyproject.toml:148) but
**not** in the spine `layers` list:

```toml
layers = [
    "comms",
    "payments",
    "reservations",
    "pricing",
    "properties",
    "integrations",
    "accounts",
]
```

So its import edges are completely unconstrained. The config's own comment
about `integrations` names the hazard exactly: "it MUST be listed, or its
position is unconstrained and a future upward edge … goes uncaught". Today
`owners` only reaches into `properties` (`owners/views/properties.py:17–18`)
plus `core`/`accounts` — slotting it in now is free; waiting lets edges
accrete until the slot-in forces refactors.

## Proposed fix

Add `owners` to the `layers` list between `reservations` and `pricing` (it
reads property/pricing data and will be read by reservations/payments for
owner approval flows). Run `uv run lint-imports`; fix any violations
surfaced (none expected today).

## Acceptance

- `owners` appears in the layers contract; `lint-imports` passes in CI.

## Dependencies

None. Related: Q-017 also touches the layers list (comms position).

## Resolution (2026-06-15)

`owners` added to the spine `layers` list **between `reservations` and
`pricing`**, exactly as proposed. Position confirmed from its actual edges:

- `owners` imports **down** only — `owners → properties`
  (`serializers/property.py`, `views/properties.py`) and `owners → accounts`
  (`scoping.py`, `permissions.py`, `views/me.py`, `factories.py`).
- `reservations` imports **down** into `owners` — `reservations.views.owner →
  owners.{permissions,scoping}`, plus the `demo_ical` management command.

So `owners` must sit below `reservations` and above `properties`/`accounts`;
the reservations/pricing slot satisfies both. `uv run lint-imports` passes
with **2 kept, 0 broken** and **no source imports needed fixing** (all edges
were already clean downward edges). Added an explanatory comment block above
the `layers` list mirroring the `integrations` rationale, and updated the
spine diagram in `django_res/CLAUDE.md`.

Full gate green: `pytest` (1706 passed), `ruff check`, `ruff format --check`,
`mypy` (no issues), import-linter.
