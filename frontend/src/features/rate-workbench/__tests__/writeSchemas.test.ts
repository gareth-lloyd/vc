import { describe, expect, it } from "vitest";
import { discountWriteInputSchema, extraWriteInputSchema } from "../schemas";

describe("extraWriteInputSchema", () => {
  it("requires a name", () => {
    expect(extraWriteInputSchema.safeParse({ name: "" }).success).toBe(false);
    expect(extraWriteInputSchema.safeParse({ name: "Transfer" }).success).toBe(true);
  });

  it("rejects an end date before the start date", () => {
    const bad = extraWriteInputSchema.safeParse({
      name: "X",
      applies_from: "2026-08-01",
      applies_to: "2026-07-01",
    });
    expect(bad.success).toBe(false);
    const ok = extraWriteInputSchema.safeParse({
      name: "X",
      applies_from: "2026-07-01",
      applies_to: "2026-08-01",
    });
    expect(ok.success).toBe(true);
  });
});

describe("discountWriteInputSchema", () => {
  it("requires a name and rejects a reversed validity range", () => {
    expect(discountWriteInputSchema.safeParse({ name: "" }).success).toBe(false);
    expect(
      discountWriteInputSchema.safeParse({
        name: "Early",
        valid_from: "2026-08-01",
        valid_to: "2026-07-01",
      }).success,
    ).toBe(false);
  });

  it("does not carry uses_count into the parsed write shape (read-only field)", () => {
    const parsed = discountWriteInputSchema.parse({ name: "Early", max_uses: 5 });
    expect("uses_count" in parsed).toBe(false);
  });
});
