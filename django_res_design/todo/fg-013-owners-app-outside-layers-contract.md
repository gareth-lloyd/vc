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
