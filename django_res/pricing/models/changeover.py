"""ChangeOverRule lives in the `properties` app.

Per the design spec the actual model is owned by `properties` (alongside
property settings) and is referenced from `pricing` via a string FK at
quote time. This shim file is intentionally empty so the import surface
mirrors the documented `pricing.models.changeover` slot without redefining
anything.
"""

from __future__ import annotations
