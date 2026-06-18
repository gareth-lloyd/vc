import { describe, expect, it } from "vitest";
import {
  PROPERTY_CONTACT_ROLES,
  availabilityBlockWriteInputSchema,
  availabilityCellSchema,
  propertyContactAssignmentWriteInputSchema,
  propertyCreateInputSchema,
  propertyDetailSchema,
  propertyListItemSchema,
  propertyListResponseSchema,
  propertyRoomWriteInputSchema,
  rateCardWriteInputSchema,
  rateRuleWriteInputSchema,
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

describe("propertyCreateInputSchema", () => {
  const valid = {
    name: "Villa Aurora",
    display_name: "Villa Aurora",
    slug: "villa-aurora",
    category: 1,
    group: 2,
    region: 3,
  };

  it("accepts the six required fields", () => {
    expect(propertyCreateInputSchema.parse(valid)).toMatchObject(valid);
  });

  it("rejects a blank name", () => {
    const result = propertyCreateInputSchema.safeParse({ ...valid, name: "  " });
    expect(result.success).toBe(false);
  });

  it("rejects an unselected FK (the 0 sentinel)", () => {
    for (const field of ["category", "group", "region"] as const) {
      const result = propertyCreateInputSchema.safeParse({ ...valid, [field]: 0 });
      expect(result.success, field).toBe(false);
    }
  });

  it("rejects a slug with invalid characters", () => {
    const result = propertyCreateInputSchema.safeParse({ ...valid, slug: "Villa Aurora!" });
    expect(result.success).toBe(false);
  });

  it("accepts a slug with digits and dashes", () => {
    expect(propertyCreateInputSchema.parse({ ...valid, slug: "villa-23-aurora" }).slug).toBe(
      "villa-23-aurora",
    );
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

  it("accepts every allowed role", () => {
    for (const role of PROPERTY_CONTACT_ROLES) {
      const result = propertyContactAssignmentWriteInputSchema.parse({ contact: 1, role });
      expect(result.role).toBe(role);
    }
  });

  it("requires role and rejects values outside the enum", () => {
    expect(() => propertyContactAssignmentWriteInputSchema.parse({ contact: 1 })).toThrow();
    expect(() =>
      propertyContactAssignmentWriteInputSchema.parse({ contact: 1, role: "cleaner" }),
    ).toThrow();
    expect(() =>
      propertyContactAssignmentWriteInputSchema.parse({ contact: 1, role: "" }),
    ).toThrow();
  });
});

describe("rateCardWriteInputSchema", () => {
  const valid = { name: "Standard", min_nights: 3 };

  it("accepts a minimal card", () => {
    const result = rateCardWriteInputSchema.parse(valid);
    expect(result.name).toBe("Standard");
  });

  it("requires a name", () => {
    expect(() => rateCardWriteInputSchema.parse({ ...valid, name: "  " })).toThrow();
  });

  it("rejects max_nights below min_nights but allows null", () => {
    expect(() => rateCardWriteInputSchema.parse({ ...valid, max_nights: 2 })).toThrow();
    expect(rateCardWriteInputSchema.parse({ ...valid, max_nights: null }).max_nights).toBeNull();
    expect(rateCardWriteInputSchema.parse({ ...valid, max_nights: 3 }).max_nights).toBe(3);
  });
});

describe("rateRuleWriteInputSchema", () => {
  const valid = {
    date_from: "2026-06-01",
    date_to: "2026-06-08",
    min_party: 1,
    max_party: 8,
    nightly: "150.00",
    weekly: "",
    is_poa: false,
  };

  it("accepts a priced rule", () => {
    expect(rateRuleWriteInputSchema.parse(valid).nightly).toBe("150.00");
  });

  it("requires date_from strictly before date_to", () => {
    expect(() => rateRuleWriteInputSchema.parse({ ...valid, date_to: "2026-06-01" })).toThrow();
    expect(rateRuleWriteInputSchema.parse({ ...valid, date_to: "2026-06-02" }).date_to).toBe(
      "2026-06-02",
    );
  });

  it("requires min_party <= max_party", () => {
    expect(() => rateRuleWriteInputSchema.parse({ ...valid, min_party: 9 })).toThrow();
    expect(rateRuleWriteInputSchema.parse({ ...valid, min_party: 8 }).min_party).toBe(8);
  });

  it("requires a price unless POA", () => {
    expect(() => rateRuleWriteInputSchema.parse({ ...valid, nightly: "", weekly: "" })).toThrow();
    expect(
      rateRuleWriteInputSchema.parse({ ...valid, nightly: "", weekly: "", is_poa: true }).is_poa,
    ).toBe(true);
    expect(rateRuleWriteInputSchema.parse({ ...valid, nightly: "", weekly: "900" }).weekly).toBe(
      "900",
    );
  });

  it("accepts a POA rule with lingering price text (payload nulls it at submit)", () => {
    expect(rateRuleWriteInputSchema.parse({ ...valid, is_poa: true }).is_poa).toBe(true);
    // Even malformed leftovers in the disabled inputs must not block a POA save.
    expect(
      rateRuleWriteInputSchema.parse({ ...valid, is_poa: true, nightly: "12.345" }).is_poa,
    ).toBe(true);
  });

  it("treats whitespace-only prices as empty", () => {
    expect(rateRuleWriteInputSchema.parse({ ...valid, nightly: " ", weekly: "900" }).nightly).toBe(
      "",
    );
    expect(() => rateRuleWriteInputSchema.parse({ ...valid, nightly: " ", weekly: "" })).toThrow();
  });

  it("validates money strings", () => {
    expect(() => rateRuleWriteInputSchema.parse({ ...valid, nightly: "12,50" })).toThrow();
    expect(() => rateRuleWriteInputSchema.parse({ ...valid, nightly: "12.345" })).toThrow();
    expect(() => rateRuleWriteInputSchema.parse({ ...valid, nightly: "-5" })).toThrow();
    expect(rateRuleWriteInputSchema.parse({ ...valid, nightly: "1250" }).nightly).toBe("1250");
    expect(rateRuleWriteInputSchema.parse({ ...valid, nightly: "12.5" }).nightly).toBe("12.5");
  });
});

describe("propertyRoomWriteInputSchema", () => {
  const beds = {
    double: 1,
    twin_double: 0,
    twin: 0,
    single: 0,
    bunk: 0,
    sofa: 0,
    childrens: 0,
  };
  const valid = {
    name: "Master",
    placement: "main_house" as const,
    website_description: "",
    vc_notes: "",
    is_ensuite: true,
    beds,
  };

  it("accepts a fully specified room", () => {
    const result = propertyRoomWriteInputSchema.parse(valid);
    expect(result.beds).toEqual(beds);
  });

  it("saves a room with just a name (beds omitted, GAP-024)", () => {
    const result = propertyRoomWriteInputSchema.parse({
      name: "Master",
      placement: "main_house" as const,
      website_description: "",
      vc_notes: "",
      is_ensuite: true,
    });
    expect(result.beds).toBeUndefined();
    expect(result.name).toBe("Master");
  });

  it("still rejects a blank name", () => {
    expect(() => propertyRoomWriteInputSchema.parse({ ...valid, name: "  " })).toThrow();
  });

  it("keeps empty description/notes as '' so a PATCH can clear them", () => {
    // Regression guard: these must stay `z.string()` (not `.optional()`), or an
    // empty value would be omitted from the payload and silently stop clearing.
    const result = propertyRoomWriteInputSchema.parse(valid);
    expect(result.website_description).toBe("");
    expect(result.vc_notes).toBe("");
    // `undefined` is rejected (the field is required), proving it is NOT optional.
    expect(() =>
      propertyRoomWriteInputSchema.parse({ ...valid, website_description: undefined }),
    ).toThrow();
  });
});
