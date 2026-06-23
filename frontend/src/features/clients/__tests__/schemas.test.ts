import { describe, expect, it } from "vitest";
import { clientListItemSchema, clientsListResponseSchema } from "../schemas";

describe("clientListItemSchema", () => {
  it("parses a full row and ignores extra (region) fields", () => {
    const parsed = clientListItemSchema.parse({
      id: 7,
      title: "Mr",
      first_name: "Alan",
      last_name: "Turing",
      primary_email: "alan@example.com",
      primary_phone: "+44 7700 900222",
      is_agent: true,
      status: "active",
      quoted_region_slugs: ["tuscany"],
      booked_region_slugs: ["amalfi"],
    });
    expect(parsed.id).toBe(7);
    expect(parsed.is_agent).toBe(true);
  });

  it("accepts null primary channels", () => {
    const parsed = clientListItemSchema.parse({
      id: 8,
      first_name: "Edith",
      last_name: "Clarke",
      primary_email: null,
      primary_phone: null,
      is_agent: false,
      status: "inactive",
    });
    expect(parsed.primary_email).toBeNull();
  });

  it("rejects an unknown status", () => {
    expect(() =>
      clientListItemSchema.parse({ id: 1, first_name: "X", is_agent: false, status: "bogus" }),
    ).toThrow();
  });

  it("parses a paginated response", () => {
    const page = clientsListResponseSchema.parse({
      count: 1,
      next: null,
      previous: null,
      results: [{ id: 1, first_name: "A", last_name: "B", is_agent: false, status: "active" }],
    });
    expect(page.results).toHaveLength(1);
  });
});
