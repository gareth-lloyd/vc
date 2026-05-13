import { describe, expect, it } from "vitest";
import {
  quotationDetailSchema,
  quotationLineSchema,
  quotationListItemSchema,
  quotationListResponseSchema,
} from "../schemas";

describe("quotation schemas", () => {
  it("parses a minimal list item", () => {
    const parsed = quotationListItemSchema.parse({
      id: 1,
      reference: "Q-001",
      status: "draft",
    });
    expect(parsed.id).toBe(1);
    expect(parsed.status).toBe("draft");
  });

  it("accepts unknown status values without crashing (loose status)", () => {
    const parsed = quotationListItemSchema.parse({
      id: 2,
      reference: "Q-002",
      status: "negotiating",
    });
    expect(parsed.status).toBe("negotiating");
  });

  it("parses a detail with empty lines", () => {
    const parsed = quotationDetailSchema.parse({
      id: 3,
      reference: "Q-003",
      status: "sent",
    });
    expect(parsed.lines).toEqual([]);
    expect(parsed.cancel_reason).toBe("");
  });

  it("parses a line with string total (DRF decimal serialisation)", () => {
    const parsed = quotationLineSchema.parse({
      id: 10,
      total: "1234.50",
    });
    expect(parsed.total).toBe("1234.50");
  });

  it("parses a paginated list response", () => {
    const parsed = quotationListResponseSchema.parse({
      count: 1,
      next: null,
      previous: null,
      results: [{ id: 1, reference: "Q-001", status: "draft" }],
    });
    expect(parsed.count).toBe(1);
    expect(parsed.results[0].reference).toBe("Q-001");
  });
});
