import { describe, expect, it } from "vitest";
import { resolveDragRange } from "../dragRange";

// Occupied days are NOT selectable; everything else is.
const blocked = (...isos: string[]) => {
  const set = new Set(isos);
  return (iso: string) => !set.has(iso);
};
const allSelectable = () => true;

describe("resolveDragRange", () => {
  it("maps a forward drag to a half-open range (date_to exclusive)", () => {
    expect(resolveDragRange("2026-06-10", "2026-06-13", allSelectable)).toEqual({
      date_from: "2026-06-10",
      date_to: "2026-06-14",
    });
  });

  it("normalises a reverse drag to the same range", () => {
    expect(resolveDragRange("2026-06-13", "2026-06-10", allSelectable)).toEqual({
      date_from: "2026-06-10",
      date_to: "2026-06-14",
    });
  });

  it("treats a single-day drag as a one-night range", () => {
    expect(resolveDragRange("2026-06-10", "2026-06-10", allSelectable)).toEqual({
      date_from: "2026-06-10",
      date_to: "2026-06-11",
    });
  });

  it("truncates a forward drag before the first occupied day, anchored on the origin", () => {
    // Press 10th, drag to 15th, but the 13th is occupied → stops at the 12th.
    expect(resolveDragRange("2026-06-10", "2026-06-15", blocked("2026-06-13"))).toEqual({
      date_from: "2026-06-10",
      date_to: "2026-06-13",
    });
  });

  it("truncates a reverse drag before the first occupied day on the moving side", () => {
    // Press 15th, drag back to 10th, but the 12th is occupied → stops at the 13th.
    expect(resolveDragRange("2026-06-15", "2026-06-10", blocked("2026-06-12"))).toEqual({
      date_from: "2026-06-13",
      date_to: "2026-06-16",
    });
  });

  it("returns null when the origin day itself is not selectable", () => {
    expect(resolveDragRange("2026-06-13", "2026-06-15", blocked("2026-06-13"))).toBeNull();
  });
});
