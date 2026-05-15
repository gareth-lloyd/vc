"""Tiny console helpers for management-command output."""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def render_table(header: Sequence[object], rows: Iterable[Sequence[object]]) -> str:
    """Render a fixed-width text table with a dashed underline under the header.

    Cells are ``str()``-coerced and columns are padded to their widest cell.
    Returns the whole block as a single string (no trailing newline) ready for
    one ``stdout.write()``.
    """
    matrix = [[str(c) for c in header]] + [[str(c) for c in r] for r in rows]
    widths = [max(len(c) for c in col) for col in zip(*matrix, strict=True)]
    lines = ["  ".join(c.ljust(w) for c, w in zip(matrix[0], widths, strict=True))]
    lines.append("  ".join("-" * w for w in widths))
    lines += ["  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)) for row in matrix[1:]]
    return "\n".join(lines)
