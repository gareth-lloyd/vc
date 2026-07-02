import { describe, expect, it } from "vitest";
import { format } from "date-fns";
import { disabledDaysFromCells } from "./disabledDays";

const cells = [
  { date: "2026-07-04", available: false, block_id: null },
  { date: "2026-07-05", available: false, block_id: 42 },
  { date: "2026-07-06", available: true, block_id: null },
  // Older payload shapes omit block_id entirely.
  { date: "2026-07-07", available: false },
];

const iso = (dates: Date[]) => dates.map((d) => format(d, "yyyy-MM-dd"));

describe("disabledDaysFromCells", () => {
  it("create mode disables every occupied day — including block_id: null cells", () => {
    // Regression: the real API sends block_id: null on booked cells, which
    // collided with the create-mode null sentinel and left them selectable.
    expect(iso(disabledDaysFromCells(cells))).toEqual(["2026-07-04", "2026-07-05", "2026-07-07"]);
  });

  it("edit mode keeps only the edited block's own days selectable", () => {
    expect(iso(disabledDaysFromCells(cells, 42))).toEqual(["2026-07-04", "2026-07-07"]);
  });

  it("never disables available days", () => {
    expect(disabledDaysFromCells([{ date: "2026-07-06", available: true, block_id: 9 }])).toEqual(
      [],
    );
  });
});
