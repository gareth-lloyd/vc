import { describe, expect, it } from "vitest";
import { hasAnyFilter, multiAvailabilityResponseSchema } from "../schemas";

describe("multiAvailabilityResponseSchema", () => {
  it("parses records + bookings", () => {
    const parsed = multiAvailabilityResponseSchema.parse({
      records: [
        {
          id: 1,
          property: 7,
          date_from: "2026-06-10",
          date_to: "2026-06-17",
          expires_at: null,
          released_at: null,
          reason: "owner_block",
          notes: "",
          created_at: "2026-06-01T00:00:00Z",
        },
      ],
      bookings: [
        {
          id: 9,
          property: 7,
          date_from: "2026-06-20",
          date_to: "2026-06-27",
          status: "awaiting_deposit",
          reference: "VC1234",
          guest_name: "Ada Lovelace",
        },
      ],
    });
    expect(parsed.records).toHaveLength(1);
    expect(parsed.bookings[0].reference).toBe("VC1234");
  });

  it("accepts a null guest_name", () => {
    const parsed = multiAvailabilityResponseSchema.parse({
      records: [],
      bookings: [
        {
          id: 9,
          property: 7,
          date_from: "2026-06-20",
          date_to: "2026-06-27",
          status: "draft",
          reference: "VC1",
          guest_name: null,
        },
      ],
    });
    expect(parsed.bookings[0].guest_name).toBeNull();
  });
});

describe("hasAnyFilter — the force-filter gate", () => {
  it("is false with no filters (page/window position do not count)", () => {
    expect(hasAnyFilter({})).toBe(false);
    expect(hasAnyFilter({ page: 3 })).toBe(false);
  });

  it("is true when any one filter is set", () => {
    expect(hasAnyFilter({ q: "casa" })).toBe(true);
    expect(hasAnyFilter({ country: "ES" })).toBe(true);
    expect(hasAnyFilter({ region: "ibiza" })).toBe(true);
    expect(hasAnyFilter({ collection: "signature" })).toBe(true);
    expect(hasAnyFilter({ min_bedrooms: 4 })).toBe(true);
    expect(hasAnyFilter({ status: "active" })).toBe(true);
  });

  it("ignores empty-string filters", () => {
    expect(hasAnyFilter({ q: "", country: "" })).toBe(false);
  });
});
