import { describe, expect, it } from "vitest";
import type { QueryParams } from "@/lib/api/url";
import { fromFeaturesParam, toFeaturesParam } from "../api";

describe("toFeaturesParam", () => {
  it("comma-joins multiple slugs into a single scalar string", () => {
    expect(toFeaturesParam(["a", "b"])).toBe("a,b");
  });

  it("returns a single slug unchanged", () => {
    expect(toFeaturesParam(["pool"])).toBe("pool");
  });

  it("returns undefined for an empty or missing array", () => {
    expect(toFeaturesParam([])).toBeUndefined();
    expect(toFeaturesParam(undefined)).toBeUndefined();
  });

  it("type-checks as a scalar QueryValue, not an array", () => {
    // `buildQuery` (lib/api/url.ts) serializes a string[] as REPEATED query
    // keys (?features=a&features=b); the backend's `filter_features` reads a
    // single `request.GET.get("features")`, so a raw array here would
    // silently degrade the AND-filter to "only the last selected feature".
    // This assignment fails to compile if `toFeaturesParam` ever returns
    // string[] again.
    const query: QueryParams = { features: toFeaturesParam(["a", "b"]) };
    expect(query.features).toBe("a,b");
  });

  it("trims whitespace and drops duplicates before joining", () => {
    // Guards a hand-edited/bookmarked URL (`?features=pool, pool`) from
    // producing a mangled CSV — see fromFeaturesParam below for the other
    // half of this contract.
    expect(toFeaturesParam([" pool ", "pool", "sea-view"])).toBe("pool,sea-view");
  });
});

describe("fromFeaturesParam", () => {
  it("splits a comma-joined param into slugs", () => {
    expect(fromFeaturesParam("pool,sea-view")).toEqual(["pool", "sea-view"]);
  });

  it("trims whitespace and drops blank/duplicate segments", () => {
    expect(fromFeaturesParam("pool, pool ,, sea-view")).toEqual(["pool", "sea-view"]);
  });

  it("returns an empty array for null, undefined, or an empty string", () => {
    expect(fromFeaturesParam(null)).toEqual([]);
    expect(fromFeaturesParam(undefined)).toEqual([]);
    expect(fromFeaturesParam("")).toEqual([]);
  });

  it("round-trips through toFeaturesParam", () => {
    const slugs = ["pool", "sea-view"];
    expect(fromFeaturesParam(toFeaturesParam(slugs))).toEqual(slugs);
  });
});
