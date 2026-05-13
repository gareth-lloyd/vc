import { describe, expect, it } from "vitest";
import {
  bookingDetailSchema,
  bookingEventSchema,
  bookingListItemSchema,
  bookingListResponseSchema,
  bookingNoteKindSchema,
  bookingNoteSchema,
  bookingNoteVisibilitySchema,
  bookingNoteWriteInputSchema,
  bookingStatusSchema,
  cancelBookingInputSchema,
  declineBookingInputSchema,
  modifyDatesInputSchema,
  modifyGuestsInputSchema,
} from "../schemas";

const baseListItem = {
  id: 51,
  reference: "B-AAA-001",
  status: "deposit_paid" as const,
  property: 12,
  guest: 99,
  agent: null,
  assigned_to: null,
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  adults: 4,
  children: 2,
  currency: 1,
  rental_price: "1500.00",
  balance_due: "1000.00",
  balance_due_at: "2026-06-01",
  site_source: "main_website",
  is_archived: false,
  archived_at: null,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-02T00:00:00Z",
};

describe("bookingStatusSchema", () => {
  it("accepts the 11 known statuses", () => {
    for (const s of [
      "draft",
      "pending_owner_approval",
      "awaiting_deposit",
      "deposit_paid",
      "awaiting_balance",
      "balance_paid",
      "checked_in",
      "checked_out",
      "cancelled",
      "expired",
      "declined",
    ]) {
      expect(bookingStatusSchema.parse(s)).toBe(s);
    }
  });

  it("rejects unknown values", () => {
    expect(() => bookingStatusSchema.parse("unknown")).toThrow();
  });
});

describe("bookingListItemSchema", () => {
  it("parses a payload without denormalised name fields", () => {
    const parsed = bookingListItemSchema.parse(baseListItem);
    expect(parsed.reference).toBe("B-AAA-001");
    expect(parsed.property_name).toBeUndefined();
  });

  it("parses a payload WITH denormalised name fields", () => {
    const parsed = bookingListItemSchema.parse({
      ...baseListItem,
      property_name: "Casa Norte",
      guest_name: "Ada Lovelace",
      guest_email: "ada@example.com",
      currency_code: "GBP",
      total: "2500.00",
      night_count: 7,
    });
    expect(parsed.property_name).toBe("Casa Norte");
    expect(parsed.guest_email).toBe("ada@example.com");
    expect(parsed.night_count).toBe(7);
  });
});

describe("bookingListResponseSchema", () => {
  it("parses a paginated wrapper", () => {
    const parsed = bookingListResponseSchema.parse({
      count: 1,
      next: null,
      previous: null,
      results: [baseListItem],
    });
    expect(parsed.results).toHaveLength(1);
  });
});

describe("bookingDetailSchema", () => {
  it("extends list with detail-only fields", () => {
    const parsed = bookingDetailSchema.parse({
      ...baseListItem,
      pricing_snapshot: { rate_subtotal: "1500.00" },
      discount: "0.00",
      adjustment: "0.00",
      terms_version: 1,
      terms_accepted_at: "2026-05-01T00:00:00Z",
      payment_method: "card",
      cancel_reason: "",
      cancelled_at: null,
    });
    expect(parsed.payment_method).toBe("card");
  });
});

describe("bookingEventSchema", () => {
  it("parses a timeline event", () => {
    const parsed = bookingEventSchema.parse({
      id: 10,
      booking: 51,
      from_status: "awaiting_deposit",
      to_status: "deposit_paid",
      actor: 1,
      source: "webhook",
      reason: "",
      meta: { payment_id: 42 },
      created_at: "2026-05-02T12:00:00Z",
    });
    expect(parsed.to_status).toBe("deposit_paid");
    expect(parsed.meta).toMatchObject({ payment_id: 42 });
  });

  it("accepts a null from_status for the creation row", () => {
    const parsed = bookingEventSchema.parse({
      id: 1,
      from_status: null,
      to_status: "draft",
      actor: null,
      source: "system",
      created_at: "2026-05-01T00:00:00Z",
    });
    expect(parsed.from_status).toBeNull();
    expect(parsed.reason).toBe("");
  });
});

describe("bookingNoteKindSchema", () => {
  it("accepts the four kinds", () => {
    for (const k of ["general", "internal", "concierge", "villa"]) {
      expect(bookingNoteKindSchema.parse(k)).toBe(k);
    }
  });

  it("rejects unknown kinds", () => {
    expect(() => bookingNoteKindSchema.parse("urgent")).toThrow();
  });
});

describe("bookingNoteVisibilitySchema", () => {
  it("accepts the three visibilities", () => {
    for (const v of ["staff_only", "owner", "guest"]) {
      expect(bookingNoteVisibilitySchema.parse(v)).toBe(v);
    }
  });

  it("rejects unknown visibilities", () => {
    expect(() => bookingNoteVisibilitySchema.parse("public")).toThrow();
  });
});

describe("bookingNoteSchema", () => {
  it("parses a server note payload with the tightened enums", () => {
    const parsed = bookingNoteSchema.parse({
      id: 7,
      booking: 51,
      author: 1,
      kind: "concierge",
      body: "Owner prefers airport pickup at 14:00.",
      is_pinned: true,
      visibility: "owner",
      created_at: "2026-05-02T08:00:00Z",
      updated_at: "2026-05-02T08:00:00Z",
    });
    expect(parsed.kind).toBe("concierge");
    expect(parsed.visibility).toBe("owner");
    expect(parsed.is_pinned).toBe(true);
  });

  it("rejects unknown kind values loudly", () => {
    expect(() =>
      bookingNoteSchema.parse({
        id: 7,
        kind: "urgent",
        body: "x",
        visibility: "staff_only",
      }),
    ).toThrow();
  });
});

describe("bookingNoteWriteInputSchema", () => {
  const validBase = {
    kind: "general" as const,
    visibility: "staff_only" as const,
    is_pinned: false,
  };

  it("rejects an empty body", () => {
    const result = bookingNoteWriteInputSchema.safeParse({ ...validBase, body: "" });
    expect(result.success).toBe(false);
  });

  it("rejects a whitespace-only body", () => {
    const result = bookingNoteWriteInputSchema.safeParse({ ...validBase, body: "   " });
    expect(result.success).toBe(false);
  });

  it("trims whitespace from body", () => {
    const parsed = bookingNoteWriteInputSchema.parse({ ...validBase, body: "  hello  " });
    expect(parsed.body).toBe("hello");
  });

  it("parses a fully-specified write input", () => {
    const parsed = bookingNoteWriteInputSchema.parse({
      ...validBase,
      kind: "concierge",
      visibility: "owner",
      is_pinned: true,
      body: "hi",
    });
    expect(parsed.kind).toBe("concierge");
    expect(parsed.visibility).toBe("owner");
    expect(parsed.is_pinned).toBe(true);
  });
});

describe("cancelBookingInputSchema", () => {
  it("accepts an empty/undefined reason", () => {
    expect(cancelBookingInputSchema.parse({}).reason).toBeUndefined();
    expect(cancelBookingInputSchema.parse({ reason: "" }).reason).toBe("");
  });

  it("trims whitespace from reason", () => {
    expect(cancelBookingInputSchema.parse({ reason: "  guest no-show  " }).reason).toBe(
      "guest no-show",
    );
  });

  it("rejects a reason over 500 characters", () => {
    const result = cancelBookingInputSchema.safeParse({ reason: "x".repeat(501) });
    expect(result.success).toBe(false);
  });

  it("accepts a reason at exactly 500 characters", () => {
    const result = cancelBookingInputSchema.safeParse({ reason: "x".repeat(500) });
    expect(result.success).toBe(true);
  });
});

describe("declineBookingInputSchema", () => {
  it("rejects an empty reason", () => {
    expect(declineBookingInputSchema.safeParse({ reason: "" }).success).toBe(false);
  });

  it("rejects a whitespace-only reason", () => {
    expect(declineBookingInputSchema.safeParse({ reason: "   " }).success).toBe(false);
  });

  it("trims and accepts a valid reason", () => {
    expect(declineBookingInputSchema.parse({ reason: "  owner declined  " }).reason).toBe(
      "owner declined",
    );
  });

  it("rejects a reason over 500 characters", () => {
    expect(declineBookingInputSchema.safeParse({ reason: "x".repeat(501) }).success).toBe(false);
  });
});

describe("modifyDatesInputSchema", () => {
  it("rejects when date_to is before date_from", () => {
    expect(
      modifyDatesInputSchema.safeParse({
        date_from: "2026-07-10",
        date_to: "2026-07-05",
      }).success,
    ).toBe(false);
  });

  it("rejects when date_to equals date_from", () => {
    expect(
      modifyDatesInputSchema.safeParse({
        date_from: "2026-07-10",
        date_to: "2026-07-10",
      }).success,
    ).toBe(false);
  });

  it("accepts when date_to is after date_from", () => {
    const parsed = modifyDatesInputSchema.parse({
      date_from: "2026-07-10",
      date_to: "2026-07-17",
    });
    expect(parsed.date_from).toBe("2026-07-10");
    expect(parsed.date_to).toBe("2026-07-17");
  });

  it("accepts an optional reason", () => {
    const parsed = modifyDatesInputSchema.parse({
      date_from: "2026-07-10",
      date_to: "2026-07-17",
      reason: "guest request",
    });
    expect(parsed.reason).toBe("guest request");
  });

  it("rejects missing dates", () => {
    expect(modifyDatesInputSchema.safeParse({ date_from: "", date_to: "2026-07-17" }).success).toBe(
      false,
    );
  });
});

describe("modifyGuestsInputSchema", () => {
  it("rejects adults < 1", () => {
    expect(modifyGuestsInputSchema.safeParse({ adults: 0 }).success).toBe(false);
  });

  it("rejects non-integer adults", () => {
    expect(modifyGuestsInputSchema.safeParse({ adults: 2.5 }).success).toBe(false);
  });

  it("rejects negative children", () => {
    expect(modifyGuestsInputSchema.safeParse({ adults: 2, children: -1 }).success).toBe(false);
  });

  it("accepts adults with optional children and reason", () => {
    const parsed = modifyGuestsInputSchema.parse({
      adults: 3,
      children: 1,
      reason: "extra guest",
    });
    expect(parsed.adults).toBe(3);
    expect(parsed.children).toBe(1);
    expect(parsed.reason).toBe("extra guest");
  });

  it("accepts adults alone", () => {
    const parsed = modifyGuestsInputSchema.parse({ adults: 2 });
    expect(parsed.adults).toBe(2);
  });
});
