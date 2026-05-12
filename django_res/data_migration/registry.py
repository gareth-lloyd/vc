"""Explicit registry of loaders, keyed by short name.

Kept manual on purpose — autodiscovery would hide load order and make
dependency-aware orchestration harder to reason about.
"""

from __future__ import annotations

from data_migration.base import BaseLoader
from data_migration.loaders.country import CountryLoader

LOADERS: dict[str, type[BaseLoader]] = {
    CountryLoader.name: CountryLoader,
}
