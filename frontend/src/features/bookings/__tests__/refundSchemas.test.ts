import { describe, expect, it } from "vitest";
import {
  refundMethodLabel,
  refundMethodSchema,
  refundPurposeTrackLabel,
  refundPurposeTrackSchema,
  refundReasonCodeLabel,
  refundReasonCodeSchema,
  refundRequestInputSchema,
  refundSchema,
  refundsListSchema,
  refundStatusLabel,
  refundStatusSchema,
} from "../schemas";

// A complete server row — every Refund field the serializer emits, so the
// schema is exercised at full width (and proves no `currency_code` is required).
const fullRefund = {
  id: 4,
  reference: "RF-000004",
  booking: 51,
  against_payment: null,
  purpose_track: "balance",
  amount: "250.00",
  currency: 1,
  status: "pending",
  reason_code: "overpayment",
  reason_notes: "Guest paid twice",
  method: "online_gateway",
  requested_by: 9,
  requested_at: "2026-06-01T00:00:00Z",
  approved_by: null,
  approved_at: null,
  rejected_by: null,
  rejected_at: null,
  rejection_reason: "",
  executed_by: null,
  executed_at: null,
  cancelled_at: null,
  settled_at: null,
  failure_reason: "",
  meta: {},
  security_deposit: null,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

describe("refundStatusSchema", () => {
  it("accepts the seven workflow statuses", () => {
    for (const s of [
      "pending",
      "approved",
      "rejected",
      "executing",
      "succeeded",
      "failed",
      "cancelled",
    ]) {
      expect(refundStatusSchema.parse(s)).toBe(s);
    }
  });

  it("rejects unknown values loudly", () => {
    expect(() => refundStatusSchema.parse("settled")).toThrow();
  });
});

describe("refundMethodSchema / refundReasonCodeSchema / refundPurposeTrackSchema", () => {
  it("accepts the three methods", () => {
    for (const m of ["online_gateway", "manual_bank_transfer", "offline"]) {
      expect(refundMethodSchema.parse(m)).toBe(m);
    }
  });

  it("accepts the six reason codes", () => {
    for (const c of [
      "cancellation",
      "overpayment",
      "goodwill",
      "security_deposit_release",
      "duplicate_charge",
      "other",
    ]) {
      expect(refundReasonCodeSchema.parse(c)).toBe(c);
    }
  });

  it("accepts the five purpose tracks", () => {
    for (const p of ["deposit", "balance", "security_deposit", "adjustment", "goodwill"]) {
      expect(refundPurposeTrackSchema.parse(p)).toBe(p);
    }
  });
});

describe("refundSchema", () => {
  it("parses a full server row with no currency_code", () => {
    const parsed = refundSchema.parse(fullRefund);
    expect(parsed.reference).toBe("RF-000004");
    expect(parsed.currency).toBe(1);
    expect(parsed.requested_by).toBe(9);
    expect(parsed).not.toHaveProperty("currency_code");
  });

  it("parses a terminal executed row", () => {
    const parsed = refundSchema.parse({
      ...fullRefund,
      status: "succeeded",
      approved_by: 2,
      approved_at: "2026-06-02T00:00:00Z",
      executed_by: 3,
      executed_at: "2026-06-03T00:00:00Z",
      settled_at: "2026-06-03T00:00:00Z",
    });
    expect(parsed.status).toBe("succeeded");
    expect(parsed.settled_at).toBe("2026-06-03T00:00:00Z");
  });

  it("parses the booking refunds list as a plain array", () => {
    const parsed = refundsListSchema.parse([fullRefund, { ...fullRefund, id: 5 }]);
    expect(parsed).toHaveLength(2);
    expect(parsed[1].id).toBe(5);
  });
});

describe("refundRequestInputSchema", () => {
  const base = {
    amount: "250.00",
    purpose_track: "balance" as const,
    reason_code: "overpayment" as const,
    method: "online_gateway" as const,
    reason_notes: "",
  };

  it("accepts a valid request", () => {
    expect(refundRequestInputSchema.safeParse(base).success).toBe(true);
  });

  it("rejects a zero or malformed amount", () => {
    for (const amount of ["0", "0.00", "-5", "abc", "1.555", ""]) {
      expect(refundRequestInputSchema.safeParse({ ...base, amount }).success).toBe(false);
    }
  });

  it("rejects an unknown reason_code", () => {
    expect(refundRequestInputSchema.safeParse({ ...base, reason_code: "whoops" }).success).toBe(
      false,
    );
  });
});

describe("refund label resolvers", () => {
  it("return non-empty, non-key strings for every enum value", () => {
    for (const value of refundStatusSchema.options) {
      const label = refundStatusLabel(value);
      expect(label).toBeTruthy();
      expect(label).not.toContain("labels.refund_status");
    }
    for (const value of refundMethodSchema.options) {
      expect(refundMethodLabel(value)).toBeTruthy();
    }
    for (const value of refundReasonCodeSchema.options) {
      expect(refundReasonCodeLabel(value)).toBeTruthy();
    }
    for (const value of refundPurposeTrackSchema.options) {
      expect(refundPurposeTrackLabel(value)).toBeTruthy();
    }
  });
});
