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
      "7",
      "descriptions",
    ]);
    expect(queryKeys.properties.features(7)).toEqual(["properties", "detail", "7", "features"]);
    expect(queryKeys.properties.rooms(7)).toEqual(["properties", "detail", "7", "rooms"]);
  });

  it("bookings keys branch off detail consistently", () => {
    expect(queryKeys.bookings.all()).toEqual(["bookings"]);
    expect(queryKeys.bookings.lists()).toEqual(["bookings", "list"]);
    expect(queryKeys.bookings.list({ q: "x" })).toEqual(["bookings", "list", { q: "x" }]);
    expect(queryKeys.bookings.detail(7)).toEqual(["bookings", "detail", "7"]);
    expect(queryKeys.bookings.activity(7)).toEqual(["bookings", "detail", "7", "activity"]);
    expect(queryKeys.bookings.notes(7)).toEqual(["bookings", "detail", "7", "notes"]);
    expect(queryKeys.bookings.conciergeItems(7)).toEqual([
      "bookings",
      "detail",
      "7",
      "concierge-items",
    ]);
  });

  it("invalidation-root factories are prefixes of their filtered/ranged variants", () => {
    // properties.lists() must prefix list(filters); bookingsRoot must prefix
    // bookingsInRange; contacts.details() must prefix every contact detail
    // subtree — invalidateQueries matches by prefix.
    expect(queryKeys.properties.lists()).toEqual(["properties", "list"]);
    expect(queryKeys.properties.list({ q: "x" }).slice(0, 2)).toEqual(queryKeys.properties.lists());
    expect(queryKeys.properties.bookingsRoot(7)).toEqual(["properties", "detail", "7", "bookings"]);
    expect(queryKeys.properties.bookingsInRange(7, "2026-01-01", "2026-02-01").slice(0, 4)).toEqual(
      queryKeys.properties.bookingsRoot(7),
    );
    expect(queryKeys.contacts.details()).toEqual(["contacts", "detail"]);
    expect(queryKeys.contacts.detail(3).slice(0, 2)).toEqual(queryKeys.contacts.details());
    expect(queryKeys.contacts.bookings(3).slice(0, 2)).toEqual(queryKeys.contacts.details());
  });

  it("normalizes id-bearing keys so string and number ids hash identically", () => {
    // A detail page reads the id from the URL (always a string) while mutation
    // success handlers write the cache with entity.id (a number). React Query
    // hashes keys via JSON.stringify, so these must produce equal keys or the
    // fresh data lands on an orphan entry the layout never observes.
    expect(queryKeys.bookings.detail(51)).toEqual(queryKeys.bookings.detail("51"));
    expect(queryKeys.bookings.activity(51)).toEqual(queryKeys.bookings.activity("51"));
    expect(queryKeys.properties.detail(12)).toEqual(queryKeys.properties.detail("12"));
    expect(queryKeys.contacts.detail(3)).toEqual(queryKeys.contacts.detail("3"));
    expect(queryKeys.enquiries.detail(8)).toEqual(queryKeys.enquiries.detail("8"));
    expect(queryKeys.quotations.detail(4)).toEqual(queryKeys.quotations.detail("4"));
  });
});
