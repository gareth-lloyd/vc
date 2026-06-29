import { describe, expect, it } from "vitest";
import { isActionAvailable, type BookingAction } from "../status";
import { bookingStatusSchema, type BookingDetail, type BookingStatus } from "../schemas";

const TERMINAL: ReadonlySet<BookingStatus> = new Set([
  "checked_out",
  "cancelled",
  "expired",
  "declined",
]);

const STATUS_BASED: Record<
  Exclude<BookingAction, "archive" | "restore">,
  ReadonlySet<BookingStatus>
> = {
  confirm: new Set(["draft", "pending_owner_approval"]),
  cancel: new Set([
    "draft",
    "pending_owner_approval",
    "awaiting_deposit",
    "deposit_paid",
    "awaiting_balance",
    "balance_paid",
  ]),
  owner_decline: new Set(["pending_owner_approval"]),
  modify_dates: new Set(["awaiting_deposit", "deposit_paid", "awaiting_balance", "balance_paid"]),
  modify_guests: new Set([
    "draft",
    "pending_owner_approval",
    "awaiting_deposit",
    "deposit_paid",
    "awaiting_balance",
    "balance_paid",
  ]),
  check_in: new Set(["balance_paid"]),
  check_out: new Set(["checked_in"]),
  resend_confirmation: new Set([
    "draft",
    "pending_owner_approval",
    "awaiting_deposit",
    "deposit_paid",
    "awaiting_balance",
    "balance_paid",
    "checked_in",
  ]),
};

function makeBooking(status: BookingStatus, is_archived = false): BookingDetail {
  return {
    id: 1,
    reference: "B-X",
    status,
    property: 1,
    agent: null,
    assigned_to: null,
    date_from: "2026-07-01",
    date_to: "2026-07-08",
    adults: 2,
    children: 0,
    currency: 1,
    rental_price: "0",
    balance_due: "0",
    balance_due_at: null,
    site_source: "main_website",
    is_archived,
    archived_at: null,
    created_at: null,
    updated_at: null,
  };
}

describe("isActionAvailable — status-based actions", () => {
  for (const action of Object.keys(STATUS_BASED) as Array<keyof typeof STATUS_BASED>) {
    for (const status of bookingStatusSchema.options) {
      const expected = STATUS_BASED[action].has(status);
      it(`${action} on ${status} (not archived) => ${expected}`, () => {
        expect(isActionAvailable(action, makeBooking(status))).toBe(expected);
      });
    }
  }
});

describe("isActionAvailable — archive", () => {
  for (const status of bookingStatusSchema.options) {
    const expected = !TERMINAL.has(status) ? false : true;
    it(`archive on ${status} (not archived) => ${expected}`, () => {
      expect(isActionAvailable("archive", makeBooking(status, false))).toBe(expected);
    });
    it(`archive on ${status} (already archived) => false`, () => {
      expect(isActionAvailable("archive", makeBooking(status, true))).toBe(false);
    });
  }
});

describe("isActionAvailable — restore", () => {
  it("is true when booking is archived (any status)", () => {
    for (const status of bookingStatusSchema.options) {
      expect(isActionAvailable("restore", makeBooking(status, true))).toBe(true);
    }
  });

  it("is false when booking is not archived (any status)", () => {
    for (const status of bookingStatusSchema.options) {
      expect(isActionAvailable("restore", makeBooking(status, false))).toBe(false);
    }
  });
});
