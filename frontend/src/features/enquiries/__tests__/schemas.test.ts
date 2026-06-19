import { describe, expect, it } from "vitest";
import {
  enquiryDetailSchema,
  enquiryListItemSchema,
  enquiryStatusSchema,
  enquiryWriteInputSchema,
} from "../schemas";

describe("enquiryStatusSchema", () => {
  it("parses each known status", () => {
    for (const s of ["new", "contacted", "quoted", "lost", "converted"] as const) {
      expect(enquiryStatusSchema.parse(s)).toBe(s);
    }
  });

  it("rejects unknown statuses", () => {
    expect(enquiryStatusSchema.safeParse("won").success).toBe(false);
    expect(enquiryStatusSchema.safeParse("").success).toBe(false);
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
});

describe("enquiryDetailSchema", () => {
  const base = {
    id: 1,
    reference: "E-AAA-001",
    status: "quoted",
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
