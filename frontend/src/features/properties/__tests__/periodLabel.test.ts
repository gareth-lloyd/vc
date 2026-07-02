import { describe, expect, it } from "vitest";

import { periodLabel } from "../periodLabel";

describe("periodLabel (GAP-059 — the one shared fallback rule)", () => {
  it("prefers the operator name", () => {
    expect(periodLabel({ name: "Peak", date_from: "2026-06-01", date_to: "2026-06-30" })).toBe(
      "Peak",
    );
  });

  it.each(["", null, undefined])(
    "falls back to the compact date span for a blank name (%j)",
    (name) => {
      expect(periodLabel({ name, date_from: "2026-06-01", date_to: "2026-06-30" })).toBe(
        "1–30 Jun",
      );
    },
  );
});
