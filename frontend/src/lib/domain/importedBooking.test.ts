import { describe, expect, it } from "vitest";
import { formatDateRangeEndpoints } from "@/lib/format/date";
import { type ImportedBooking, importedBookingWhen, recordedAmount } from "./importedBooking";

function row(overrides: Partial<ImportedBooking> = {}): ImportedBooking {
  return {
    id: 1,
    booking_number: "BN500",
    villa_name: "Villa Yeraki",
    property: null,
    property_name: null,
    destination: "",
    year: 2019,
    notes: "",
    date_from: null,
    date_to: null,
    amount: null,
    currency_code: null,
    ...overrides,
  };
}

describe("recordedAmount", () => {
  it("is null when no amount was recorded", () => {
    expect(recordedAmount(row())).toBeNull();
  });

  it("formats with the recorded currency", () => {
    expect(recordedAmount(row({ amount: "4250.00", currency_code: "GBP" }))).toBe("£4,250.00");
  });

  it("shows the bare number when legacy recorded no currency", () => {
    expect(recordedAmount(row({ amount: "900" }))).toBe("900.00");
  });
});

describe("importedBookingWhen", () => {
  it("prefers the exact dates", () => {
    const dated = row({ date_from: "2025-08-03", date_to: "2025-08-10", year: 2025 });
    expect(importedBookingWhen(dated)).toBe(formatDateRangeEndpoints("2025-08-03", "2025-08-10"));
  });

  it("falls back to the year", () => {
    expect(importedBookingWhen(row({ year: 2017 }))).toBe("2017");
  });

  it("is null when neither dates nor year are known", () => {
    expect(importedBookingWhen(row({ year: null }))).toBeNull();
  });
});
