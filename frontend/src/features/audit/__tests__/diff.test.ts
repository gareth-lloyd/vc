import { describe, expect, it } from "vitest";
import { interpretEntry } from "../diff";

describe("interpretEntry", () => {
  it("reads a plain update as [old, new] rows", () => {
    const result = interpretEntry({ commission_amount: ["10.00", "12.50"] });
    expect(result.action).toBe("updated");
    expect(result.rows).toEqual([{ field: "commission_amount", before: "10.00", after: "12.50" }]);
    expect(result.mergedInto).toBeUndefined();
  });

  it("treats an all-null before side as an update (backend writes no create marker)", () => {
    // A create row is {field: [null, value], ...}; the backend does not mark it,
    // so we render it honestly as a change rather than guessing "created".
    const result = interpretEntry({ first_name: [null, "Ada"], last_name: [null, "Lovelace"] });
    expect(result.action).toBe("updated");
    expect(result.rows).toHaveLength(2);
    expect(result.rows[0]).toEqual({ field: "first_name", before: null, after: "Ada" });
  });

  it("flags a deletion and strips the __deleted__ control key from rows", () => {
    const result = interpretEntry({
      __deleted__: true,
      reference: ["VC-0001", null],
    });
    expect(result.action).toBe("deleted");
    expect(result.rows).toEqual([{ field: "reference", before: "VC-0001", after: null }]);
  });

  it("flags a merge and surfaces target + rewrite counts", () => {
    const result = interpretEntry({
      __deleted__: true,
      __merged_into__: "42",
      __rewrites__: { "reservations.Booking.guest": 3, "comms.EmailLog.person": 1 },
      email: ["ada@example.com", null],
    });
    expect(result.action).toBe("merged");
    expect(result.mergedInto).toBe("42");
    expect(result.rewrites).toEqual({
      "reservations.Booking.guest": 3,
      "comms.EmailLog.person": 1,
    });
    expect(result.rows).toEqual([{ field: "email", before: "ada@example.com", after: null }]);
  });

  it("keeps a redacted sentinel verbatim for the renderer to translate", () => {
    const result = interpretEntry({ tax_number: ["[REDACTED]", "[REDACTED]"] });
    expect(result.rows[0]).toEqual({
      field: "tax_number",
      before: "[REDACTED]",
      after: "[REDACTED]",
    });
  });

  it("is defensive: a non-pair value becomes a single after-only row", () => {
    const result = interpretEntry({ weird: "not-a-pair" });
    expect(result.rows).toEqual([{ field: "weird", before: undefined, after: "not-a-pair" }]);
  });

  it("returns no rows for an empty diff", () => {
    expect(interpretEntry({}).rows).toEqual([]);
    expect(interpretEntry({}).action).toBe("updated");
  });
});
