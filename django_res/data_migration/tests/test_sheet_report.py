"""GAP-113: `SheetReport` names the rows behind a category, not just a count."""

from __future__ import annotations

from data_migration.sheets.report import SheetReport


def test_ids_are_recorded_per_category_and_rendered_in_order() -> None:
    report = SheetReport("import_archive_stays")

    report.add_id("ambiguous", "110")
    report.add_id("ambiguous", "57/94")
    report.add_id("dates_dropped", "28")

    assert report.ids == {"ambiguous": ["110", "57/94"], "dates_dropped": ["28"]}
    rendered = report.render()
    assert "110, 57/94" in rendered
    assert "dates_dropped" in rendered


def test_no_ids_renders_no_id_block() -> None:
    assert "Ids" not in SheetReport("import_past_bookers").render()


def test_ids_roll_back_with_the_row_that_recorded_them() -> None:
    # A row noting an id mid-way and then raising is rolled back to its
    # savepoint; its ids must go with its counts.
    report = SheetReport("x")
    report.add_id("dates_dropped", "28")
    snapshot = report.row_counts()
    report.add_id("dates_dropped", "61")
    report.add_id("target_taken", "7")

    report.restore_row_counts(snapshot)

    assert report.ids == {"dates_dropped": ["28"]}
