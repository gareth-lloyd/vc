import { describe, expect, it } from "vitest";
import {
  quotationDetailSchema,
  quotationLineSchema,
  quotationListItemSchema,
  quotationListResponseSchema,
  quotationLineWriteInputSchema,
  quotationPreviewSchema,
  quoteOptionSchema,
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

  it("parses a line with the new pricing fields", () => {
    const parsed = quotationLineSchema.parse({
      id: 10,
      total: "1234.50",
      discount: "100.00",
      inclusions: "Daily housekeeping",
      price_override_reason: "Agreed rate",
      hero_image_url: "https://cdn.example/villa.jpg",
    });
    expect(parsed.discount).toBe("100.00");
    expect(parsed.inclusions).toBe("Daily housekeeping");
    expect(parsed.hero_image_url).toBe("https://cdn.example/villa.jpg");
  });

  it("defaults inclusions/reason and tolerates a null hero image", () => {
    const parsed = quotationLineSchema.parse({ id: 11, hero_image_url: null });
    expect(parsed.inclusions).toBe("");
    expect(parsed.price_override_reason).toBe("");
    expect(parsed.hero_image_url).toBeNull();
  });

  it("parses a quote option carrying a hero image url", () => {
    const parsed = quoteOptionSchema.parse({
      property_id: 5,
      property_name: "Villa Sol",
      available: true,
      hero_image_url: "https://cdn.example/sol.jpg",
    });
    expect(parsed.hero_image_url).toBe("https://cdn.example/sol.jpg");
  });

  it("parses the guest-facing preview shape", () => {
    const parsed = quotationPreviewSchema.parse({
      html: "<html><body>Quote</body></html>",
      subject: "Your villa quote",
      intro: "Dear guest",
      signoff: "Kind regards",
    });
    expect(parsed.html).toContain("Quote");
    expect(parsed.subject).toBe("Your villa quote");
  });

  it("requires a price override reason for a manual line write", () => {
    const result = quotationLineWriteInputSchema.safeParse({
      property: 1,
      date_from: "2026-07-01",
      date_to: "2026-07-08",
      adults: 2,
      children: 0,
      is_manual: true,
      total: "999.00",
      price_override_reason: "  ",
      notes: "",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toContain("price_override_reason");
    }
  });

  it("rejects a manual line write with a missing total", () => {
    const result = quotationLineWriteInputSchema.safeParse({
      property: 1,
      date_from: "2026-07-01",
      date_to: "2026-07-08",
      adults: 2,
      children: 0,
      is_manual: true,
      // total omitted
      price_override_reason: "Agreed rate",
      notes: "",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.path.includes("total"))).toBe(true);
    }
  });

  it("rejects a manual line write with a blank or non-positive total", () => {
    for (const total of ["", "   ", "0", "-5", "abc"]) {
      const result = quotationLineWriteInputSchema.safeParse({
        property: 1,
        date_from: "2026-07-01",
        date_to: "2026-07-08",
        adults: 2,
        children: 0,
        is_manual: true,
        total,
        price_override_reason: "Agreed rate",
        notes: "",
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues.some((i) => i.path.includes("total"))).toBe(true);
      }
    }
  });

  it("accepts a manual line write with a positive total and a reason", () => {
    const result = quotationLineWriteInputSchema.safeParse({
      property: 1,
      date_from: "2026-07-01",
      date_to: "2026-07-08",
      adults: 2,
      children: 0,
      is_manual: true,
      total: "999.00",
      price_override_reason: "Agreed rate",
      notes: "",
    });
    expect(result.success).toBe(true);
  });

  it("allows a non-manual line write without total or reason", () => {
    const result = quotationLineWriteInputSchema.safeParse({
      property: 1,
      date_from: "2026-07-01",
      date_to: "2026-07-08",
      adults: 2,
      children: 0,
      is_manual: false,
      notes: "",
    });
    expect(result.success).toBe(true);
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
