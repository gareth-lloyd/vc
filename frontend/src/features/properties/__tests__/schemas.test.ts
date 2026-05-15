import { describe, expect, it } from "vitest";
import {
  availabilityBlockWriteInputSchema,
  availabilityCellSchema,
  propertyContactAssignmentWriteInputSchema,
  propertyDetailSchema,
  propertyListItemSchema,
  propertyListResponseSchema,
} from "../schemas";

describe("availabilityCellSchema", () => {
  it("parses a whole-day cell without segments", () => {
    const cell = availabilityCellSchema.parse({
      date: "2026-06-01",
      available: false,
      reason: "owner_block",
      block_id: 7,
    });
    expect(cell.segments).toBeUndefined();
    expect(cell.block_id).toBe(7);
  });

  it("parses a split changeover cell with am/pm segments", () => {
    const cell = availabilityCellSchema.parse({
      date: "2026-06-08",
      available: false,
      reason: "booked",
      block_id: null,
      segments: {
        am: { available: false, reason: "booked", block_id: null },
        pm: { available: false, reason: "owner_block", block_id: 9 },
      },
    });
    expect(cell.segments?.am.reason).toBe("booked");
    expect(cell.segments?.pm.block_id).toBe(9);
  });
});

describe("availabilityBlockWriteInputSchema", () => {
  it("rejects a non-editable reason", () => {
    const result = availabilityBlockWriteInputSchema.safeParse({
      reason: "quotation_open",
      date_from: "2026-06-01",
      date_to: "2026-06-05",
    });
    expect(result.success).toBe(false);
  });

  it("rejects date_to <= date_from", () => {
    const result = availabilityBlockWriteInputSchema.safeParse({
      reason: "manual",
      date_from: "2026-06-05",
      date_to: "2026-06-05",
    });
    expect(result.success).toBe(false);
  });

  it("accepts a valid manual block", () => {
    const result = availabilityBlockWriteInputSchema.safeParse({
      reason: "manual",
      date_from: "2026-06-01",
      date_to: "2026-06-05",
      notes: "Owner stay",
    });
    expect(result.success).toBe(true);
  });
});

describe("propertyListItemSchema", () => {
  it("parses a minimal list payload", () => {
    expect(
      propertyListItemSchema.parse({
        id: 1,
        name: "Casa Norte",
        status: "active",
      }),
    ).toMatchObject({ id: 1, name: "Casa Norte" });
  });
});

describe("propertyListResponseSchema", () => {
  it("parses a paginated wrapper", () => {
    const parsed = propertyListResponseSchema.parse({
      count: 2,
      next: null,
      previous: null,
      results: [
        { id: 1, name: "A", status: "active" },
        { id: 2, name: "B", status: "draft" },
      ],
    });
    expect(parsed.results).toHaveLength(2);
  });
});

describe("propertyDetailSchema", () => {
  it("defaults feature_ids when omitted", () => {
    const parsed = propertyDetailSchema.parse({
      id: 5,
      name: "Villa Azul",
      status: "active",
    });
    expect(parsed.feature_ids).toEqual([]);
  });
});

describe("propertyContactAssignmentWriteInputSchema", () => {
  it("accepts a valid assignment input", () => {
    const result = propertyContactAssignmentWriteInputSchema.parse({
      contact: 1,
      role: "owner",
      start_date: "2024-01-01",
      is_primary: true,
    });
    expect(result.contact).toBe(1);
  });

  it("rejects non-integer contact id", () => {
    expect(() => propertyContactAssignmentWriteInputSchema.parse({ contact: 1.5 })).toThrow();
  });

  it("trims and enforces max-length on role", () => {
    const result = propertyContactAssignmentWriteInputSchema.parse({
      contact: 1,
      role: "  owner  ",
    });
    expect(result.role).toBe("owner");

    expect(() =>
      propertyContactAssignmentWriteInputSchema.parse({ contact: 1, role: "x".repeat(121) }),
    ).toThrow();
  });
});
