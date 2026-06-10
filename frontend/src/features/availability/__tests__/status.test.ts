import { describe, expect, it } from "vitest";
import { reasonClasses } from "@/features/properties/availabilityTokens";
import { bandStatusClasses, holdDisplayStatus } from "../status";

describe("holdDisplayStatus", () => {
  it("maps owner_block and maintenance to stop_sale", () => {
    expect(holdDisplayStatus("owner_block")).toBe("stop_sale");
    expect(holdDisplayStatus("maintenance")).toBe("stop_sale");
  });

  it("maps every other live hold reason to on_hold", () => {
    expect(holdDisplayStatus("manual")).toBe("on_hold");
    expect(holdDisplayStatus("quotation_open")).toBe("on_hold");
    expect(holdDisplayStatus("booking_deposit")).toBe("on_hold");
  });
});

describe("bandStatusClasses", () => {
  // The timeline's colours come from the same token map as the single-villa
  // calendar, so the two screens' legends cannot drift.
  it("derives every display status from the shared reason token map", () => {
    expect(bandStatusClasses("booked")).toBe(reasonClasses("booked"));
    expect(bandStatusClasses("stop_sale")).toBe(reasonClasses("owner_block"));
    expect(bandStatusClasses("on_hold")).toBe(reasonClasses("quotation"));
  });
});
