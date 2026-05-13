import { describe, expect, it } from "vitest";
import { formatDate } from "./date";

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
