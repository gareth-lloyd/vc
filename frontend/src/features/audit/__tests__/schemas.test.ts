import { describe, expect, it } from "vitest";
import { auditLogEntrySchema, auditLogListResponseSchema } from "../schemas";

describe("auditLogEntrySchema", () => {
  it("parses a minimal entry", () => {
    const result = auditLogEntrySchema.parse({
      id: "11111111-1111-1111-1111-111111111111",
      entity_type: "accounts.contact",
      object_id: "42",
      actor: 7,
      actor_email: "ops@example.com",
      field_diffs: { first_name: { from: "A", to: "B" } },
      correlation_id: null,
      created_at: "2026-05-13T10:00:00Z",
    });
    expect(result.entity_type).toBe("accounts.contact");
    expect(result.actor_email).toBe("ops@example.com");
  });

  it("defaults field_diffs to {} when absent", () => {
    const result = auditLogEntrySchema.parse({
      id: "22222222-2222-2222-2222-222222222222",
      entity_type: "accounts.contact",
      object_id: "1",
      actor: null,
      actor_email: null,
      created_at: "2026-05-13T10:00:00Z",
    });
    expect(result.field_diffs).toEqual({});
  });
});

describe("auditLogListResponseSchema", () => {
  it("parses a DRF page envelope", () => {
    const result = auditLogListResponseSchema.parse({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    expect(result.results).toHaveLength(0);
  });
});
