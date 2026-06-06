import { describe, expect, it } from "vitest";
import {
  blockRequestWriteInputSchema,
  ownerBlockRequestSchema,
  ownerBookingDetailSchema,
  ownerBookingListItemSchema,
  ownerCalendarSchema,
  ownerDashboardSchema,
  ownerMeSchema,
} from "../schemas";

const baseBookingRow = {
  id: 7,
  reference: "VC-0007",
  status: "deposit_paid",
  property_id: 3,
  property_name: "Villa Anemoi",
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  adults: 4,
  children: 2,
  currency_code: "EUR",
  guest_name: "Ada Lovelace",
  guest_country: { code: "GB", name: "United Kingdom" },
  is_repeat_guest: true,
  can_approve: false,
};

describe("ownerBookingListItemSchema", () => {
  it("parses a row with money fields ABSENT (redacted)", () => {
    const parsed = ownerBookingListItemSchema.parse(baseBookingRow);
    expect(parsed.rental_price).toBeUndefined();
    expect(parsed.balance_due).toBeUndefined();
    expect(parsed.guest_country?.name).toBe("United Kingdom");
  });

  it("parses a row with money fields PRESENT (granted)", () => {
    const parsed = ownerBookingListItemSchema.parse({
      ...baseBookingRow,
      rental_price: "1500.00",
      balance_due: "1000.00",
    });
    expect(parsed.rental_price).toBe("1500.00");
    expect(parsed.balance_due).toBe("1000.00");
  });

  it("accepts null guest_country and guest_name", () => {
    const parsed = ownerBookingListItemSchema.parse({
      ...baseBookingRow,
      guest_name: null,
      guest_country: null,
    });
    expect(parsed.guest_name).toBeNull();
    expect(parsed.guest_country).toBeNull();
  });
});

describe("ownerBookingDetailSchema", () => {
  it("parses a detail with money + guest_contact ABSENT", () => {
    const parsed = ownerBookingDetailSchema.parse(baseBookingRow);
    expect(parsed.gross_total).toBeUndefined();
    expect(parsed.commission).toBeUndefined();
    expect(parsed.net_to_owner).toBeUndefined();
    expect(parsed.guest_contact).toBeUndefined();
  });

  it("parses a detail with money + guest_contact PRESENT", () => {
    const parsed = ownerBookingDetailSchema.parse({
      ...baseBookingRow,
      gross_total: "2000.00",
      commission: "400.00",
      net_to_owner: "1600.00",
      guest_contact: { email: "ada@example.com", phone: "+44 20 7946 0000" },
    });
    expect(parsed.gross_total).toBe("2000.00");
    expect(parsed.net_to_owner).toBe("1600.00");
    expect(parsed.guest_contact?.email).toBe("ada@example.com");
  });
});

describe("ownerDashboardSchema", () => {
  it("parses with null money totals (no view_full_money grant)", () => {
    const parsed = ownerDashboardSchema.parse({
      ytd: { bookings: 12, gross_revenue: null, net_to_owner: null },
      properties: { total: 3, by_status: { active: 2, draft: 1 } },
      upcoming_arrivals: [],
    });
    expect(parsed.ytd.gross_revenue).toBeNull();
    expect(parsed.properties.by_status.active).toBe(2);
  });

  it("parses with money totals present", () => {
    const parsed = ownerDashboardSchema.parse({
      ytd: { bookings: 12, gross_revenue: "50000.00", net_to_owner: "40000.00" },
      properties: { total: 3, by_status: {} },
      upcoming_arrivals: [
        {
          reference: "VC-0007",
          property_id: 3,
          property_name: "Villa Anemoi",
          date_from: "2026-07-01",
          date_to: "2026-07-08",
          guest_name: "Ada",
          adults: 2,
          children: 0,
        },
      ],
    });
    expect(parsed.ytd.gross_revenue).toBe("50000.00");
    expect(parsed.upcoming_arrivals).toHaveLength(1);
  });
});

describe("ownerMeSchema", () => {
  it("parses owner identity with per-property grants", () => {
    const parsed = ownerMeSchema.parse({
      user: {
        id: 1,
        email: "owner@example.com",
        first_name: "Kostas",
        last_name: "Papas",
        is_active: true,
        is_staff: false,
        is_superuser: false,
      },
      is_owner: true,
      organisations: [
        {
          id: 9,
          name: "Kostas Hospitality Ltd",
          role: "owner",
          properties: [{ property_id: 3, view_full_money: true, view_guest_details: false }],
        },
      ],
    });
    expect(parsed.is_owner).toBe(true);
    expect(parsed.organisations[0].properties[0].view_full_money).toBe(true);
  });
});

describe("ownerCalendarSchema", () => {
  it("parses cells with and without segments", () => {
    const parsed = ownerCalendarSchema.parse({
      property_id: 3,
      can_request_block: true,
      cells: [
        { date: "2026-07-01", available: true, reason: null },
        { date: "2026-07-02", available: false, reason: "booked" },
        {
          date: "2026-07-03",
          available: false,
          reason: "booked",
          segments: {
            am: { available: true, reason: null },
            pm: { available: false, reason: "booked" },
          },
        },
      ],
    });
    expect(parsed.cells).toHaveLength(3);
    expect(parsed.cells[2].segments?.pm.reason).toBe("booked");
  });
});

describe("ownerBlockRequestSchema", () => {
  it("parses an approved (live) block", () => {
    const parsed = ownerBlockRequestSchema.parse({
      id: 1,
      property: 3,
      date_from: "2026-08-01",
      date_to: "2026-08-08",
      kind: "owner_stay",
      notes: "Family week",
      status: "approved",
      created_at: "2026-06-03T10:00:00Z",
    });
    expect(parsed.status).toBe("approved");
    expect(parsed.kind).toBe("owner_stay");
  });

  it("rejects a removed status (pending)", () => {
    expect(() =>
      ownerBlockRequestSchema.parse({
        id: 1,
        property: 3,
        date_from: "2026-08-01",
        date_to: "2026-08-08",
        kind: "owner_stay",
        notes: "",
        status: "pending",
        created_at: "2026-06-03T10:00:00Z",
      }),
    ).toThrow();
  });

  it("rejects an unknown kind", () => {
    expect(() =>
      ownerBlockRequestSchema.parse({
        id: 1,
        property: 3,
        date_from: "2026-08-01",
        date_to: "2026-08-08",
        kind: "party",
        notes: "",
        status: "approved",
        created_at: "2026-06-03T10:00:00Z",
      }),
    ).toThrow();
  });
});

describe("blockRequestWriteInputSchema", () => {
  const base = {
    property: 3,
    date_from: "2026-08-01",
    date_to: "2026-08-08",
    kind: "owner_stay" as const,
    notes: "",
  };

  it("accepts a valid forward range", () => {
    expect(blockRequestWriteInputSchema.parse(base).date_to).toBe("2026-08-08");
  });

  it("rejects date_to not after date_from", () => {
    const result = blockRequestWriteInputSchema.safeParse({ ...base, date_to: "2026-08-01" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toEqual(["date_to"]);
    }
  });
});
