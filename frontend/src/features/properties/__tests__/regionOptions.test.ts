import { describe, expect, it } from "vitest";
import { regionOptionsForCountry } from "../regionOptions";

const regions = [
  { id: 7, country: 1, country_iso2: "ES", name: "Ibiza", slug: "ibiza", is_active: true },
  { id: 11, country: 2, country_iso2: "GR", name: "Crete", slug: "crete", is_active: true },
];

describe("regionOptionsForCountry", () => {
  it("returns all regions with ISO-suffixed labels when no country is chosen", () => {
    expect(regionOptionsForCountry(regions)).toEqual([
      { value: "7", label: "Ibiza (ES)" },
      { value: "11", label: "Crete (GR)" },
    ]);
  });

  it("scopes to the country with plain labels, case-insensitively", () => {
    // Lowercase — old bookmarks carry lowercase iso2 codes in the URL.
    expect(regionOptionsForCountry(regions, "es")).toEqual([{ value: "7", label: "Ibiza" }]);
  });

  it("keeps an out-of-scope current selection visible, ISO-labelled", () => {
    // A stale bookmark (country=ES&region=<GR id>) must still show which
    // region is filtering the results.
    expect(regionOptionsForCountry(regions, "ES", "11")).toEqual([
      { value: "11", label: "Crete (GR)" },
      { value: "7", label: "Ibiza" },
    ]);
  });
});
