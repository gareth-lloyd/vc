"""Declarative loader: most legacy→new mappings are just column renames.

Subclass `DeclarativeLoader` and set:
- `legacy_table`: e.g. "VillaCurrency"
- `target_model`: e.g. pricing.Currency
- `field_map`: dict[legacy_col, target_field] for simple renames
- `fk_map`: dict[legacy_col, (target_model, target_field)] — looked up by legacy_id
- override `transform_extra(row, kwargs)` for any per-row custom logic
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import Model

from data_migration.base import BaseLoader


class FkLookupError(Exception):
    pass


class DeclarativeLoader(BaseLoader):
    legacy_table: ClassVar[str] = ""
    field_map: ClassVar[dict[str, str]] = {}
    fk_map: ClassVar[dict[str, tuple[type[Model], str]]] = {}
    skip_if_missing_fk: ClassVar[bool] = False

    @property
    def legacy_query(self) -> str:  # type: ignore[override]
        cols = {self.legacy_pk_column, *self.field_map.keys(), *self.fk_map.keys()}
        return f"SELECT {', '.join(sorted(cols))} FROM {self.legacy_table}"

    def transform(self, row: dict[str, Any]) -> dict[str, Any] | None:
        kwargs: dict[str, Any] = {}
        for legacy_col, target_field in self.field_map.items():
            kwargs[target_field] = row.get(legacy_col)

        for legacy_col, (target_model, target_field) in self.fk_map.items():
            legacy_fk = row.get(legacy_col)
            if legacy_fk is None:
                kwargs[target_field] = None
                continue
            obj = target_model._default_manager.filter(legacy_id=str(legacy_fk)).first()
            if obj is None:
                if self.skip_if_missing_fk:
                    return None
                raise FkLookupError(
                    f"{self.legacy_table}.{legacy_col}={legacy_fk} -> "
                    f"{target_model.__name__}.legacy_id not found",
                )
            kwargs[target_field] = obj

        return self.transform_extra(row, kwargs)

    def transform_extra(
        self,
        row: dict[str, Any],
        kwargs: dict[str, Any],
    ) -> dict[str, Any] | None:
        return kwargs
