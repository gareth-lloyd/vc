import { describe, expect, it } from "vitest";
import {
  contestWriteInputSchema,
  ownerBlockUpdateSchema,
  ownerBlockUpdatesResponseSchema,
} from "../schemas";

function update(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    kind: "created",
    actor: 9,
    created_at: "2026-06-03T10:00:00Z",
    block: {
      id: 50,
      property: 3,
      property_name: "Villa Anemoi",
      date_from: "2026-08-01",
      date_to: "2026-08-08",
      kind: "owner_stay",
      notes: "Family week",
      status: "approved",
      created_by: 9,
    },
    contested: null,
    is_seen: false,
    ...overrides,
  };
}

describe("ownerBlockUpdateSchema", () => {
  it("parses an update with contested null", () => {
    const parsed = ownerBlockUpdateSchema.parse(update());
    expect(parsed.kind).toBe("created");
    expect(parsed.contested).toBeNull();
    expect(parsed.block.property_name).toBe("Villa Anemoi");
    expect(parsed.is_seen).toBe(false);
  });

  it("parses an update with a contested object", () => {
    const parsed = ownerBlockUpdateSchema.parse(
      update({
        kind: "cancelled",
        is_seen: true,
        contested: { at: "2026-06-04T08:00:00Z", by: 12, reason: "Double booked" },
      }),
    );
    expect(parsed.contested?.reason).toBe("Double booked");
    expect(parsed.contested?.by).toBe(12);
  });

  it("accepts null actor and null block property", () => {
    const parsed = ownerBlockUpdateSchema.parse(
      update({ actor: null, block: { ...update().block, property: null, property_name: null } }),
    );
    expect(parsed.actor).toBeNull();
    expect(parsed.block.property).toBeNull();
  });

  it("rejects an unknown block status", () => {
    expect(() =>
      ownerBlockUpdateSchema.parse(update({ block: { ...update().block, status: "pending" } })),
    ).toThrow();
  });
});

describe("ownerBlockUpdatesResponseSchema", () => {
  it("parses a DRF paginated envelope", () => {
    const parsed = ownerBlockUpdatesResponseSchema.parse({
      count: 1,
      next: null,
      previous: null,
      results: [update()],
    });
    expect(parsed.results).toHaveLength(1);
  });
});

describe("contestWriteInputSchema", () => {
  it("accepts a non-blank reason", () => {
    expect(contestWriteInputSchema.parse({ reason: "Conflict" }).reason).toBe("Conflict");
  });

  it("rejects a blank reason with an i18n key", () => {
    const result = contestWriteInputSchema.safeParse({ reason: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("updates.errors.reason_required");
    }
  });
});
