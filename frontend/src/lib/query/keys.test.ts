import { describe, expect, it } from "vitest";
import { queryKeys } from "./keys";

describe("queryKeys", () => {
  it("auth.me is stable", () => {
    expect(queryKeys.auth.me()).toEqual(queryKeys.auth.me());
    expect(queryKeys.auth.me()).toEqual(["auth", "me"]);
  });

  it("properties.list distinguishes by filters", () => {
    const a = queryKeys.properties.list({ q: "casa" });
    const b = queryKeys.properties.list({ q: "casa" });
    const c = queryKeys.properties.list({ q: "villa" });
    expect(a).toEqual(b);
    expect(a).not.toEqual(c);
  });

  it("properties.detail nests filter under id", () => {
    expect(queryKeys.properties.detail("casa-norte")).toEqual([
      "properties",
      "detail",
      "casa-norte",
    ]);
  });

  it("property sub-resources branch off the detail key", () => {
    expect(queryKeys.properties.descriptions(7)).toEqual([
      "properties",
      "detail",
      7,
      "descriptions",
    ]);
    expect(queryKeys.properties.features(7)).toEqual(["properties", "detail", 7, "features"]);
    expect(queryKeys.properties.rooms(7)).toEqual(["properties", "detail", 7, "rooms"]);
  });

  it("bookings keys branch off detail consistently", () => {
    expect(queryKeys.bookings.all()).toEqual(["bookings"]);
    expect(queryKeys.bookings.lists()).toEqual(["bookings", "list"]);
    expect(queryKeys.bookings.list({ q: "x" })).toEqual(["bookings", "list", { q: "x" }]);
    expect(queryKeys.bookings.detail(7)).toEqual(["bookings", "detail", 7]);
    expect(queryKeys.bookings.activity(7)).toEqual(["bookings", "detail", 7, "activity"]);
    expect(queryKeys.bookings.notes(7)).toEqual(["bookings", "detail", 7, "notes"]);
    expect(queryKeys.bookings.conciergeItems(7)).toEqual([
      "bookings",
      "detail",
      7,
      "concierge-items",
    ]);
  });
});
