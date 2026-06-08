import { describe, expect, it } from "vitest";
import { guestEnquiryHistorySchema, guestSchema, guestsSearchResponseSchema } from "../schemas";

describe("guestSchema", () => {
  it("parses a full active guest", () => {
    const guest = guestSchema.parse({
      id: 1,
      first_name: "Ada",
      last_name: "Lovelace",
      email: "ada@example.com",
      phone: "+447911123456",
      contact_method: "phone",
      status: "active",
    });
    expect(guest.contact_method).toBe("phone");
  });

  it("accepts a null email (phone-only guest)", () => {
    const guest = guestSchema.parse({
      id: 2,
      first_name: "Alan",
      last_name: "Turing",
      email: null,
      phone: "+447911000000",
      status: "active",
    });
    expect(guest.email).toBeNull();
  });

  it("rejects an unknown status", () => {
    expect(() =>
      guestSchema.parse({
        id: 3,
        first_name: "X",
        last_name: "Y",
        email: "x@y.com",
        status: "deleted",
      }),
    ).toThrow();
  });
});

describe("guestEnquiryHistorySchema", () => {
  it("parses a converted row with a booking", () => {
    const row = guestEnquiryHistorySchema.parse({
      id: 10,
      reference: "E-2026-000010",
      status: "converted",
      site_source: "main_website",
      request_type: "quote",
      created_at: "2026-06-01T00:00:00Z",
      quote_count: 2,
      converted_booking: { reference: "VC1234", status: "deposit_paid" },
    });
    expect(row.quote_count).toBe(2);
    expect(row.converted_booking?.reference).toBe("VC1234");
  });

  it("parses an unconverted row with a null booking", () => {
    const row = guestEnquiryHistorySchema.parse({
      id: 11,
      reference: "E-2026-000011",
      status: "quoted",
      quote_count: 1,
      converted_booking: null,
    });
    expect(row.converted_booking).toBeNull();
  });
});

describe("guestsSearchResponseSchema", () => {
  it("parses a paginated search page", () => {
    const page = guestsSearchResponseSchema.parse({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: 1,
          first_name: "Ada",
          last_name: "Lovelace",
          email: "ada@example.com",
          status: "active",
        },
      ],
    });
    expect(page.results).toHaveLength(1);
  });
});
