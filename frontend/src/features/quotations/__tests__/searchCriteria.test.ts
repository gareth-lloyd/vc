import { describe, expect, it } from "vitest";
import { quoteSearchFormSchema, type QuoteSearchForm } from "../schemas";
import { enquiryToSearchForm, searchFormToCriteria } from "../searchCriteria";

// A valid baseline form; tests override the fields under exercise.
const FORM: QuoteSearchForm = {
  arrive_from: "2026-07-04",
  arrive_to: "2026-07-10",
  weeks: 1,
  specific_date: false,
  adults: 2,
  children: 0,
  country: "",
  region: "",
  min_bedrooms: null,
  max_bedrooms: null,
  q: "",
};

describe("searchFormToCriteria", () => {
  it("even window: lands the backend's symmetric span exactly on [arrive_from, arrive_to]", () => {
    // W = 6 → flex 3, preferred arrival = arrive_from + 3. The backend searches
    // preferred ± flex ⇒ arrivals in [2026-07-04, 2026-07-10] — never earlier
    // than arrive_from.
    const criteria = searchFormToCriteria(FORM);
    expect(criteria.flex_days).toBe(3);
    expect(criteria.date_from).toBe("2026-07-07");
    expect(criteria.date_to).toBe("2026-07-14");
  });

  it("odd window: overshoots at most one day late, never early", () => {
    // W = 5 → flex 3 (ceil), preferred = arrive_from + 3 ⇒ span
    // [2026-07-04, 2026-07-10] = [arrive_from, arrive_to + 1].
    const criteria = searchFormToCriteria({ ...FORM, arrive_to: "2026-07-09" });
    expect(criteria.flex_days).toBe(3);
    expect(criteria.date_from).toBe("2026-07-07");
  });

  it("specific date: flex 0 and the exact arrival, ignoring arrive_to", () => {
    const criteria = searchFormToCriteria({
      ...FORM,
      specific_date: true,
      arrive_to: "2026-08-30",
    });
    expect(criteria.flex_days).toBe(0);
    expect(criteria.date_from).toBe("2026-07-04");
    expect(criteria.date_to).toBe("2026-07-11");
  });

  it("weeks set the preferred stay length in nights", () => {
    const criteria = searchFormToCriteria({ ...FORM, weeks: 3 });
    expect(criteria.date_to).toBe("2026-07-28"); // date_from 07-07 + 21 nights
  });

  it("carries the party and filter fields through unchanged", () => {
    const criteria = searchFormToCriteria({
      ...FORM,
      adults: 5,
      children: 2,
      country: "GR",
      region: "Corfu",
      min_bedrooms: 3,
      max_bedrooms: 6,
      q: "beach",
    });
    expect(criteria).toMatchObject({
      adults: 5,
      children: 2,
      country: "GR",
      region: "Corfu",
      min_bedrooms: 3,
      max_bedrooms: 6,
      q: "beach",
    });
  });

  it("a 42-day window maps to the backend's SEARCH_FLEX_MAX of 21", () => {
    const criteria = searchFormToCriteria({
      ...FORM,
      arrive_from: "2026-06-01",
      arrive_to: "2026-07-13",
    });
    expect(criteria.flex_days).toBe(21);
  });
});

describe("enquiryToSearchForm", () => {
  it("seeds a symmetric window from the enquiry dates and ± flexibility", () => {
    const form = enquiryToSearchForm({
      date_from: "2026-07-04",
      date_to: "2026-07-18",
      flexibility_days: 3,
      adults: 4,
      children: 1,
      min_bedrooms: 2,
    });
    expect(form).toMatchObject({
      arrive_from: "2026-07-01",
      arrive_to: "2026-07-07",
      weeks: 2,
      specific_date: false,
      adults: 4,
      children: 1,
      min_bedrooms: 2,
    });
  });

  it("round-trips: the seeded form translates back to the enquiry's own preferred date and flex", () => {
    // The enquiry's flexibility is a symmetric ± spread, so seeding then
    // translating must reproduce the exact criteria the old builder sent:
    // preferred = the enquiry's date_from, flex = flexibility_days.
    const form = enquiryToSearchForm({
      date_from: "2026-07-04",
      date_to: "2026-07-18",
      flexibility_days: 3,
      adults: 4,
      children: 1,
      min_bedrooms: 2,
    });
    const criteria = searchFormToCriteria({ ...FORM, ...form });
    expect(criteria.date_from).toBe("2026-07-04");
    expect(criteria.flex_days).toBe(3);
  });

  it("collapses to specific date when the enquiry has no flexibility", () => {
    const form = enquiryToSearchForm({
      date_from: "2026-07-04",
      date_to: "2026-07-11",
      flexibility_days: 0,
      adults: 2,
      children: 0,
      min_bedrooms: null,
    });
    expect(form).toMatchObject({
      arrive_from: "2026-07-04",
      arrive_to: "2026-07-04",
      weeks: 1,
      specific_date: true,
    });
    // Round-trip: a no-spread enquiry searches its exact date, flex 0.
    const criteria = searchFormToCriteria({ ...FORM, ...form });
    expect(criteria.date_from).toBe("2026-07-04");
    expect(criteria.flex_days).toBe(0);
  });

  it("defaults to one week when the enquiry has no dates", () => {
    const form = enquiryToSearchForm({
      date_from: null,
      date_to: null,
      flexibility_days: 0,
      adults: 2,
      children: 0,
      min_bedrooms: null,
    });
    expect(form).toMatchObject({ arrive_from: "", arrive_to: "", weeks: 1, specific_date: true });
  });

  it("rounds a non-week stay to the nearest week, floored at one", () => {
    const short = enquiryToSearchForm({
      date_from: "2026-07-04",
      date_to: "2026-07-07", // 3 nights → round(3/7) = 0 → floor to 1
      flexibility_days: 0,
      adults: 2,
      children: 0,
      min_bedrooms: null,
    });
    expect(short.weeks).toBe(1);
    const long = enquiryToSearchForm({
      date_from: "2026-07-04",
      date_to: "2026-07-22", // 18 nights → round to 3 weeks
      flexibility_days: 0,
      adults: 2,
      children: 0,
      min_bedrooms: null,
    });
    expect(long.weeks).toBe(3);
  });
});

describe("quoteSearchFormSchema", () => {
  it("accepts a valid range form", () => {
    expect(quoteSearchFormSchema.safeParse(FORM).success).toBe(true);
  });

  it("rejects arrive_to before arrive_from", () => {
    const result = quoteSearchFormSchema.safeParse({ ...FORM, arrive_to: "2026-07-01" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toEqual(["arrive_to"]);
    }
  });

  it("rejects a window wider than 42 days (flex would exceed the backend max)", () => {
    const result = quoteSearchFormSchema.safeParse({
      ...FORM,
      arrive_from: "2026-06-01",
      arrive_to: "2026-07-14", // 43 days
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toEqual(["arrive_to"]);
    }
  });

  it("requires arrive_to only when not searching a specific date", () => {
    expect(quoteSearchFormSchema.safeParse({ ...FORM, arrive_to: "" }).success).toBe(false);
    expect(
      quoteSearchFormSchema.safeParse({ ...FORM, arrive_to: "", specific_date: true }).success,
    ).toBe(true);
  });

  it("requires at least one week and one adult", () => {
    expect(quoteSearchFormSchema.safeParse({ ...FORM, weeks: 0 }).success).toBe(false);
    expect(quoteSearchFormSchema.safeParse({ ...FORM, adults: 0 }).success).toBe(false);
  });
});
