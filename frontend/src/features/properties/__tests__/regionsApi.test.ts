import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { drfPage } from "@/test/drf";
import { server } from "@/test/msw/server";
import { fetchRegions } from "../api";

const row = {
  id: 7,
  country: 1,
  country_iso2: "ES",
  name: "Ibiza",
  slug: "ibiza",
  is_active: true,
};

function captureSearch() {
  const seen: string[] = [];
  server.use(
    http.get("/api/v1/regions", ({ request }) => {
      seen.push(new URL(request.url).search);
      return HttpResponse.json(drfPage([row]));
    }),
  );
  return seen;
}

describe("fetchRegions", () => {
  it("parses is_active and passes no country params by default", async () => {
    const seen = captureSearch();
    const page = await fetchRegions();
    expect(page.results[0].is_active).toBe(true);
    expect(seen[0]).not.toContain("country");
  });

  it("sends country and country_iso2 query params when given", async () => {
    const seen = captureSearch();
    await fetchRegions({ country: 1, countryIso2: "es", hasProperties: true });
    const params = new URLSearchParams(seen[0]);
    expect(params.get("country")).toBe("1");
    expect(params.get("country_iso2")).toBe("es");
    expect(params.get("has_properties")).toBe("true");
  });
});
