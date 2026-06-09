import { describe, expect, it } from "vitest";
import { addDaysIso, formatDate } from "./date";

describe("formatDate", () => {
  it("formats an ISO string", () => {
    expect(formatDate("2026-05-14T10:00:00Z")).toBe("14 May 2026");
  });

  it("returns dash for null/undefined", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
  });

  it("returns dash for invalid input", () => {
    expect(formatDate("not-a-date")).toBe("—");
  });
});

describe("addDaysIso", () => {
  it("adds a day within a month", () => {
    expect(addDaysIso("2026-06-08", 1)).toBe("2026-06-09");
  });

  it("rolls over month and year boundaries", () => {
    expect(addDaysIso("2026-07-31", 1)).toBe("2026-08-01");
    expect(addDaysIso("2026-12-31", 1)).toBe("2027-01-01");
  });
});
