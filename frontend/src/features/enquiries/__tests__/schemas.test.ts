import { describe, expect, it } from "vitest";
import {
  enquiryDetailSchema,
  enquiryEventKindSchema,
  enquiryListItemSchema,
  enquiryStatusSchema,
  enquiryWriteInputSchema,
  leadStatusLabel,
  leadStatusSchema,
  lostReasonLabel,
  lostReasonSchema,
} from "../schemas";

describe("enquiryStatusSchema", () => {
  it("parses each known status", () => {
    for (const s of [
      "new",
      "progressing",
      "quote_sent",
      "follow_up",
      "dead",
      "converted",
    ] as const) {
      expect(enquiryStatusSchema.parse(s)).toBe(s);
    }
  });

  it("rejects unknown statuses", () => {
    expect(enquiryStatusSchema.safeParse("won").success).toBe(false);
    expect(enquiryStatusSchema.safeParse("").success).toBe(false);
  });
});

describe("leadStatusSchema", () => {
  it("parses each lead status", () => {
    for (const s of ["hot", "warm", "cold", "dead"] as const) {
      expect(leadStatusSchema.parse(s)).toBe(s);
    }
  });

  it("rejects unknown lead statuses", () => {
    expect(leadStatusSchema.safeParse("banana").success).toBe(false);
  });
});

describe("lostReasonSchema", () => {
  it("parses each lost reason", () => {
    for (const r of [
      "found_alternative",
      "availability",
      "different_destination",
      "no_group_consensus",
      "unknown",
    ] as const) {
      expect(lostReasonSchema.parse(r)).toBe(r);
    }
  });

  it("rejects unknown reasons", () => {
    expect(lostReasonSchema.safeParse("nope").success).toBe(false);
  });
});

describe("enquiryListItemSchema", () => {
  const valid = {
    id: 1,
    reference: "E-AAA-001",
    status: "new",
    guest: null,
    first_name: "Ada",
    last_name: "Lovelace",
    email: "ada@example.com",
    property: 12,
    region: null,
    date_from: "2026-07-01",
    date_to: "2026-07-08",
    adults: 2,
    children: 0,
    request_type: "quote",
    assigned_to: null,
    agent: null,
    site_source: "main_website",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-02T00:00:00Z",
  };

  it("parses a valid list item", () => {
    const parsed = enquiryListItemSchema.parse(valid);
    expect(parsed.reference).toBe("E-AAA-001");
    expect(parsed.status).toBe("new");
  });

  it("rejects rows missing required fields", () => {
    const rest = { ...valid } as Partial<typeof valid>;
    delete rest.adults;
    expect(enquiryListItemSchema.safeParse(rest).success).toBe(false);
  });

  it("rejects bad status enum values", () => {
    expect(enquiryListItemSchema.safeParse({ ...valid, status: "unknown" }).success).toBe(false);
  });

  it("parses lead_status and lost_reason when present", () => {
    const parsed = enquiryListItemSchema.parse({
      ...valid,
      status: "dead",
      lead_status: "hot",
      lost_reason: "availability",
    });
    expect(parsed.lead_status).toBe("hot");
    expect(parsed.lost_reason).toBe("availability");
  });

  it("defaults lead_status to warm and lost_reason to empty when absent", () => {
    const parsed = enquiryListItemSchema.parse(valid);
    expect(parsed.lead_status).toBe("warm");
    expect(parsed.lost_reason).toBe("");
  });

  it("rejects a bad lead_status enum value", () => {
    expect(enquiryListItemSchema.safeParse({ ...valid, lead_status: "tepid" }).success).toBe(false);
  });
});

describe("enquiryDetailSchema", () => {
  const base = {
    id: 1,
    reference: "E-AAA-001",
    status: "quote_sent",
    adults: 2,
    request_type: "quote",
    site_source: "main_website",
  };

  it("parses the nested quote-stack with lines", () => {
    const parsed = enquiryDetailSchema.parse({
      ...base,
      quotations: [
        {
          id: 10,
          reference: "QVC10",
          status: "draft",
          lines: [{ id: 100, total: "1400.00" }],
        },
      ],
    });

    expect(parsed.quotations).toHaveLength(1);
    expect(parsed.quotations[0].reference).toBe("QVC10");
    expect(parsed.quotations[0].lines).toHaveLength(1);
  });

  it("defaults quotations to an empty array when the field is absent", () => {
    const parsed = enquiryDetailSchema.parse(base);
    expect(parsed.quotations).toEqual([]);
  });

  it("parses the quotes_to_convert metric (number or null)", () => {
    expect(enquiryDetailSchema.parse({ ...base, quotes_to_convert: 3 }).quotes_to_convert).toBe(3);
    expect(
      enquiryDetailSchema.parse({ ...base, quotes_to_convert: null }).quotes_to_convert,
    ).toBeNull();
  });

  it("defaults quotes_to_convert to null when absent", () => {
    expect(enquiryDetailSchema.parse(base).quotes_to_convert).toBeNull();
  });
});

describe("enquiryEventKindSchema", () => {
  it("includes lead_status_changed", () => {
    expect(enquiryEventKindSchema.parse("lead_status_changed")).toBe("lead_status_changed");
  });
});

describe("lead status + lost reason labels", () => {
  it("maps each lead status to its English label", () => {
    expect(leadStatusLabel("hot")).toBe("Hot");
    expect(leadStatusLabel("warm")).toBe("Warm");
    expect(leadStatusLabel("cold")).toBe("Cold");
    expect(leadStatusLabel("dead")).toBe("Dead");
  });

  it("maps each lost reason to a resolved, non-empty label", () => {
    for (const r of [
      "found_alternative",
      "availability",
      "different_destination",
      "no_group_consensus",
      "unknown",
    ] as const) {
      const label = lostReasonLabel(r);
      expect(label).toBeTruthy();
      expect(label).not.toContain("lost_reason");
    }
  });
});

describe("enquiryWriteInputSchema", () => {
  const valid = {
    person: null,
    first_name: "Ada",
    last_name: "Lovelace",
    email: "ada@example.com",
    phone: "",
    date_from: "",
    date_to: "",
    is_flexible: false,
    flexibility_days: 0,
    adults: 2,
    children: 0,
    min_bedrooms: null,
    request_type: "quote",
    contact_method: null,
    site_source: "main_website",
    inbound_message: "",
  } as const;

  it("accepts a valid write input", () => {
    const parsed = enquiryWriteInputSchema.parse(valid);
    expect(parsed.adults).toBe(2);
  });

  it("requires at least one adult", () => {
    expect(enquiryWriteInputSchema.safeParse({ ...valid, adults: 0 }).success).toBe(false);
  });

  it("accepts flexibility_days in the 0–3 range and rejects outside it", () => {
    expect(enquiryWriteInputSchema.safeParse({ ...valid, flexibility_days: 3 }).success).toBe(true);
    expect(enquiryWriteInputSchema.safeParse({ ...valid, flexibility_days: 4 }).success).toBe(
      false,
    );
    expect(enquiryWriteInputSchema.safeParse({ ...valid, flexibility_days: -1 }).success).toBe(
      false,
    );
  });

  it("accepts an empty email", () => {
    const parsed = enquiryWriteInputSchema.parse({ ...valid, email: "" });
    expect(parsed.email).toBe("");
  });

  it("rejects a malformed email", () => {
    expect(enquiryWriteInputSchema.safeParse({ ...valid, email: "nope" }).success).toBe(false);
  });

  it("rejects an end date before the start date", () => {
    const result = enquiryWriteInputSchema.safeParse({
      ...valid,
      date_from: "2026-07-10",
      date_to: "2026-07-05",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toEqual(["date_to"]);
    }
  });

  it("accepts an end date equal to the start date", () => {
    expect(
      enquiryWriteInputSchema.safeParse({
        ...valid,
        date_from: "2026-07-10",
        date_to: "2026-07-10",
      }).success,
    ).toBe(true);
  });

  it("accepts a start date with no end date (dates are optional and independent)", () => {
    expect(
      enquiryWriteInputSchema.safeParse({ ...valid, date_from: "2026-07-10", date_to: "" }).success,
    ).toBe(true);
  });
});
