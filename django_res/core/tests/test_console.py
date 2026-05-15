"""Unit tests for the shared table renderer."""

from __future__ import annotations

from core.console import render_table


def test_columns_pad_to_widest_cell_including_body() -> None:
    out = render_table(
        ("a", "bb"),
        [("xxxx", "y"), ("z", "wwww")],
    ).splitlines()

    # Column 0 widens to "xxxx" (4), column 1 to "wwww" (4).
    assert out[0] == "a     bb  "
    assert out[1] == "----  ----"
    assert out[2] == "xxxx  y   "
    assert out[3] == "z     wwww"


def test_cells_are_str_coerced() -> None:
    out = render_table(("n", "pct"), [(42, "12.5")]).splitlines()
    assert out[0] == "n   pct "
    assert out[2] == "42  12.5"


def test_empty_rows_renders_header_and_underline_only() -> None:
    out = render_table(("only",), []).splitlines()
    assert out == ["only", "----"]
