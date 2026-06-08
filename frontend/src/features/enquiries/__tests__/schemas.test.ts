import { describe, expect, it } from "vitest";
import { enquiryListItemSchema, enquiryStatusSchema, enquiryWriteInputSchema } from "../schemas";

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

describe("enquiryWriteInputSchema", () => {
  const valid = {
    first_name: "Ada",
    last_name: "Lovelace",
    email: "ada@example.com",
    phone: "",
    date_from: "",
    date_to: "",
    is_flexible: false,
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

  it("accepts an empty email", () => {
    const parsed = enquiryWriteInputSchema.parse({ ...valid, email: "" });
    expect(parsed.email).toBe("");
  });

  it("rejects a malformed email", () => {
    expect(enquiryWriteInputSchema.safeParse({ ...valid, email: "nope" }).success).toBe(false);
  });
});
