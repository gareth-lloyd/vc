"""GAP-089: the per-run report both spreadsheet importers print.

Deliberately richer than `LoadReport`: skips are counted *per reason* and the
villa / person names the importer could not resolve are tallied so an operator
can fix the sheet (or the Property names) rather than guess — the ticket's
"report, don't guess" rule.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from core.console import render_table

RowCounts = tuple[tuple[Counter[str], ...], dict[str, list[str]]]


@dataclass
class SheetReport:
    name: str
    created: Counter[str] = field(default_factory=Counter)
    updated: Counter[str] = field(default_factory=Counter)
    skipped: Counter[str] = field(default_factory=Counter)
    errors: list[tuple[str, str]] = field(default_factory=list)
    unmatched_villas: Counter[str] = field(default_factory=Counter)
    unmatched_persons: Counter[str] = field(default_factory=Counter)
    #: GAP-113: the legacy ids behind a category, so a skip can be looked up
    #: rather than re-derived.
    ids: dict[str, list[str]] = field(default_factory=dict)
    rows_read: int = 0

    def add_id(self, category: str, legacy_id: str) -> None:
        self.ids.setdefault(category, []).append(legacy_id)

    def row_counts(self) -> RowCounts:
        """A copy of the per-row counters and ids, taken before a row's savepoint.

        BUG-030 §34: a row that raises is rolled back to its savepoint, so the
        counts (and ids) it made before failing must be rolled back too
        (`restore_row_counts`). `errors` is not part of the snapshot."""
        counters = tuple(
            Counter(c)
            for c in (
                self.created,
                self.updated,
                self.skipped,
                self.unmatched_villas,
                self.unmatched_persons,
            )
        )
        return counters, {category: list(ids) for category, ids in self.ids.items()}

    def restore_row_counts(self, counts: RowCounts) -> None:
        (
            (
                self.created,
                self.updated,
                self.skipped,
                self.unmatched_villas,
                self.unmatched_persons,
            ),
            self.ids,
        ) = counts

    def render(self) -> str:
        blocks = [f"== {self.name}: {self.rows_read} rows read =="]
        counts = [("created", kind, n) for kind, n in sorted(self.created.items())] + [
            ("updated", kind, n) for kind, n in sorted(self.updated.items())
        ]
        counts += [("skipped", reason, n) for reason, n in sorted(self.skipped.items())]
        blocks.append(render_table(("outcome", "what", "rows"), counts or [("-", "-", 0)]))
        if self.unmatched_villas:
            blocks.append("Unmatched villas (left unlinked):")
            blocks.append(render_table(("villa", "rows"), self.unmatched_villas.most_common()))
        if self.unmatched_persons:
            blocks.append("Unmatched persons (rows skipped):")
            blocks.append(render_table(("person", "rows"), self.unmatched_persons.most_common()))
        if self.ids:
            blocks.append("Ids by category:")
            blocks.append(
                render_table(
                    ("category", "ids"),
                    [(category, ", ".join(ids)) for category, ids in sorted(self.ids.items())],
                )
            )
        if self.errors:
            blocks.append(f"Errors ({len(self.errors)}):")
            blocks.append(render_table(("row", "error"), self.errors))
        return "\n".join(blocks)
