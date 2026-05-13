import { describe, expect, it } from "vitest";
import { isActionAllowedForStatus, type BookingAction } from "../status";
import { bookingStatusSchema, type BookingStatus } from "../schemas";

const EXPECTED: Record<BookingAction, ReadonlySet<BookingStatus>> = {
  confirm: new Set(["draft", "pending_owner_approval"]),
  cancel: new Set([
    "draft",
    "pending_owner_approval",
    "awaiting_deposit",
    "deposit_paid",
    "awaiting_balance",
    "balance_paid",
  ]),
};

describe("isActionAllowedForStatus", () => {
  for (const action of ["confirm", "cancel"] as const) {
    for (const status of bookingStatusSchema.options) {
      const expected = EXPECTED[action].has(status);
      it(`${action} on ${status} => ${expected}`, () => {
        expect(isActionAllowedForStatus(action, status)).toBe(expected);
      });
    }
  }
});
